import os
import json
import logging
import re
import time
from datetime import datetime, timezone
import feedparser
from flask import Flask, render_template
from apscheduler.schedulers.background import BackgroundScheduler
from difflib import SequenceMatcher
from openai import OpenAI

# ---------------- CONFIG ---------------- #
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("en-pole")

# Chemins
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
ARTICLES_FILE = os.path.join(STATIC_DIR, "articles.json")

# OpenAI (inchangé)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Flask
app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------------- RSS FEEDS ---------------- #
# Liste élargie (10 sources) — SkySports retiré si tu veux, mais tu peux le remettre
RSS_FEEDS = [
    "https://www.formula1.com/rss",                   # Formula1.com
    "https://www.motorsport.com/rss/f1/news/",        # Motorsport F1
    "https://www.autosport.com/f1/rss",               # Autosport F1
    "https://www.crash.net/f1/rss/news",              # Crash.net F1
    "https://www.f1i.com/feed/",                      # F1i.com
    "https://www.f1fanatic.co.uk/feed/",              # F1Fanatic
    "https://www.racefans.net/feed/",                 # RaceFans
    "https://www.grandprix247.com/feed/",             # GrandPrix247
    "https://www.thecheckeredflag.co.uk/feed/",       # The Checkered Flag
    "https://www.paddocktalk.com/rss/f1"              # PaddockTalk F1
]

# ---------------- UTILS ---------------- #
def ensure_files():
    os.makedirs(STATIC_DIR, exist_ok=True)
    if not os.path.exists(ARTICLES_FILE):
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def load_articles():
    with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_articles(articles):
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def first_sentence(text):
    """Renvoie la première phrase de text (conserve le point)."""
    if not text:
        return ""
    # couper sur . ! ? suivis d'espace ou fin de string
    parts = re.split(r'(?<=[\.\!\?])\s+', text.strip())
    return parts[0].strip() if parts else text.strip()

# ---------------- OPENAI ---------------- #
def summarize_and_translate(title, content):
    """
    Résume en UNE phrase en français et traduit le titre.
    Gère les 429 via retries & backoff, et fallback si échec.
    """
    prompt = f"""
Voici un article (titre + contenu) en anglais sur la Formule 1 :
Titre : {title}
Contenu : {content}

1) Résume le contenu en FRANÇAIS en **une seule phrase** très concise.
2) Traduis le titre en FRANÇAIS.

Répond sous la forme :
Titre: <titre en français>
Résumé: <phrase en français>
"""
    max_retries = 3
    backoff_seconds = 5
    attempt = 0

    while attempt <= max_retries:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.3,
            )
            result = response.choices[0].message.content.strip()

            # parsing robuste
            fr_title = None
            fr_summary = None
            # tenter d'extraire "Titre:" et "Résumé:" si présents
            lines = [l.strip() for l in result.splitlines() if l.strip()]
            text_joined = " ".join(lines)

            # cas où assistant renvoie "Titre: ... Résumé: ..."
            m_title = re.search(r"(?:Titre\s*[:\-]\s*)(.+?)(?:\s{2,}|Résumé\s*[:\-]|$)", text_joined, flags=re.I)
            m_summary = re.search(r"(?:Résumé\s*[:\-]\s*)(.+)$", text_joined, flags=re.I)

            if m_title:
                fr_title = m_title.group(1).strip()
            if m_summary:
                fr_summary = m_summary.group(1).strip()

            # fallback parsing si pas de tags
            if not fr_title and lines:
                fr_title = lines[0]
            if not fr_summary and len(lines) >= 2:
                fr_summary = " ".join(lines[1:])

            # garantir 1 phrase pour le résumé
            if fr_summary:
                fr_summary = first_sentence(fr_summary)
                if not fr_summary.endswith(('.', '!', '?')):
                    fr_summary += '.'
            else:
                fr_summary = ""

            # si pas de titre traduit, on utilise titre original (mais on essaie d'avoir fr_summary)
            if not fr_title:
                fr_title = title

            return fr_title, fr_summary

        except Exception as e:
            attempt += 1
            err_str = str(e)
            logger.error(f"[OpenAI] tentative {attempt} échouée : {err_str}")

            # détecter rate limit
            if ("rate limit" in err_str.lower()) or ("429" in err_str) or ("rate_limit" in err_str.lower()):
                # si on peut réessayer, attendre un peu (exponential backoff)
                if attempt <= max_retries:
                    sleep_time = backoff_seconds * (2 ** (attempt - 1))
                    logger.info(f"[OpenAI] Rate limit détectée — attente {sleep_time}s avant retry ({attempt}/{max_retries})")
                    time.sleep(sleep_time)
                    continue
                else:
                    logger.error("[OpenAI] Rate limit persistante — fallback activé")
                    break
            else:
                # autre erreur : on sort et on fallback
                logger.error("[OpenAI] Erreur non liée au rate limit, fallback activé")
                break

    # fallback : pas de traduction dispo (on renvoie titre original + extrait du contenu)
    truncated = (content or "")[:200].strip()
    if not truncated.endswith("..."):
        truncated = (truncated + "...") if len(content or "") > 200 else truncated
    return title, first_sentence(truncated)

# ---------------- LOGIQUE ---------------- #
def fetch_articles():
    logger.info("[FETCH] Début récupération RSS")
    ensure_files()
    existing = load_articles()

    new_articles = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        if getattr(feed, "bozo", 0):
            logger.warning(f"[FETCH] Problème avec le flux {feed_url} (bozo={feed.bozo})")
        # limiter le parsing pour éviter flood
        for entry in feed.entries[:5]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "") or entry.get("description", "") or ""
            date = entry.get("published") or entry.get("updated") or datetime.now(timezone.utc).isoformat()

            # Vérifier similarité par rapport aux titres existants
            found_similar = False
            for art in existing:
                if similar(title, art["title"]) > 0.7:
                    if link and link not in art.get("sources", []):
                        art.setdefault("sources", []).append(link)
                    found_similar = True
                    break

            if found_similar:
                continue

            # Nouveau -> résumer/traduire (une phrase)
            fr_title, fr_summary = summarize_and_translate(title, summary)

            new_articles.append({
                "title": fr_title,
                "summary": fr_summary,
                "date": date,
                "sources": [link] if link else []
            })

            # petite pause pour limiter la cadence d'appels OpenAI (éviter 429 brutaux)
            time.sleep(1)

    if new_articles:
        all_articles = new_articles + existing
        save_articles(all_articles)
        logger.info(f"[SAVE] {len(new_articles)} nouveaux articles sauvegardés")
    else:
        logger.info("[SAVE] Aucun nouvel article")

# ---------------- FLASK ---------------- #
@app.route("/")
def index():
    ensure_files()
    articles = load_articles()
    articles_sorted = sorted(articles, key=lambda x: x["date"], reverse=True)
    return render_template("index.html", articles=articles_sorted)

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    ensure_files()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(fetch_articles, "interval", minutes=5)
    scheduler.start()

    fetch_articles()  # première récupération immédiate

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
