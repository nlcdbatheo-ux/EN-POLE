import os
import json
import logging
import re
import html
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

import feedparser
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

# --- OpenAI (nouvelle API) ---
OPENAI_ENABLED = bool(os.environ.get("OPENAI_API_KEY"))
try:
    from openai import OpenAI
    _openai_client = OpenAI() if OPENAI_ENABLED else None
except Exception:
    _openai_client = None
    OPENAI_ENABLED = False

# ----------------- CONFIG -----------------
FEEDS = [
    ("Motorsport.com", "https://www.motorsport.com/rss/f1/news/"),
    ("Autosport",      "https://www.autosport.com/rss/f1/news/"),
    ("RaceFans",       "https://www.racefans.net/category/formula-one/feed/"),
    ("PlanetF1",       "https://planetf1.com/feed/"),
    ("GPFans",         "https://www.gpfans.com/en/rss/"),
]

MAX_PER_SOURCE        = 2      # limiter pour la mémoire
MAX_TOTAL_ARTICLES    = 80     # garder un historique raisonnable
SUMMARIES_PER_FETCH   = 2      # limiter l’usage tokens
FETCH_INTERVAL_MIN    = 60     # toutes les heures

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR    = os.path.join(BASE_DIR, "static")
ARTICLES_FILE = os.path.join(STATIC_DIR, "articles.json")

# ------------- LOGGING -------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("en-pole")

# ------------- FLASK -------------
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# ------------- UTILS -------------
def ensure_files():
    os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)
    if not os.path.exists(ARTICLES_FILE):
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def load_articles():
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_articles(new_articles):
    """Ajoute les nouveaux en haut, conserve les anciens dessous, sans doublon (par lien normalisé)."""
    old = load_articles()
    new_links = {normalize_url(a["link"]) for a in new_articles}
    merged = new_articles + [a for a in old if normalize_url(a.get("link", "")) not in new_links]

    # Tronquer l’historique pour limiter la mémoire
    merged = merged[:MAX_TOTAL_ARTICLES]

    try:
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur sauvegarde articles : {e}")

def normalize_url(u: str) -> str:
    try:
        p = urlparse(u)
        q = parse_qs(p.query)
        # enlever les params de tracking
        q = {k: v for k, v in q.items() if not k.lower().startswith("utm_")}
        p = p._replace(query=urlencode({k: v[0] if isinstance(v, list) and v else v for k, v in q.items()}))
        # enlever slash de fin
        path = p.path.rstrip("/") if p.path else p.path
        p = p._replace(path=path)
        return urlunparse(p)
    except Exception:
        return u

TAG_RE = re.compile(r"<[^>]+>")
def strip_html(text: str) -> str:
    if not text:
        return ""
    # enlever balises, décoder entités
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    # compacter espaces
    return re.sub(r"\s+", " ", text).strip()

def iso_now():
    return datetime.now(timezone.utc).isoformat()

def entry_datetime(entry):
    # feedparser peut fournir published_parsed / updated_parsed
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(entry, key, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return iso_now()

def get_entry_image(entry):
    # tenter media_content
    try:
        media = getattr(entry, "media_content", None)
        if isinstance(media, list) and media:
            if "url" in media[0]:
                return media[0]["url"]
    except Exception:
        pass
    # tenter enclosures
    try:
        if hasattr(entry, "enclosures"):
            for en in entry.enclosures:
                if getattr(en, "type", "").startswith("image"):
                    return en.href
    except Exception:
        pass
    return None

def titles_similar(a: str, b: str) -> bool:
    a = re.sub(r"[^a-z0-9]+", " ", a.lower()).strip()
    b = re.sub(r"[^a-z0-9]+", " ", b.lower()).strip()
    if not a or not b:
        return False
    # heuristique simple: si un titre contient l’autre ou longueur proche
    if a in b or b in a:
        return True
    # ratio simple sans difflib pour rester léger
    common = len(set(a.split()) & set(b.split()))
    return common >= max(3, int(min(len(a.split()), len(b.split())) * 0.6))

def dedup_articles(candidates):
    seen_links = set()
    kept = []
    for art in candidates:
        key = normalize_url(art["link"])
        if key in seen_links:
            continue
        # check similar title in kept
        duplicate = False
        for k in kept:
            if titles_similar(art["title"], k["title"]):
                duplicate = True
                break
        if not duplicate:
            kept.append(art)
            seen_links.add(key)
    return kept

def summarize_with_openai_french(title: str, raw: str) -> str | None:
    if not OPENAI_ENABLED or _openai_client is None:
        return None
    prompt = f"""Tu es un rédacteur sport auto. Résume en français, en 2 phrases claires, neutres et factuelles.
N'invente rien. Mets le pilote/écurie si pertinent. Pas d'emojis, pas de hashtags.
Titre: {title}
Texte: {raw[:1200]}"""  # borne pour limiter tokens

    try:
        resp = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu écris de courtes brèves F1 en français, style neutre."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=120,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"Erreur OpenAI : {e}")
        return None

# ------------- FETCH -------------
def fetch_articles():
    logger.info("[FETCH] Début récupération RSS")
    all_new = []
    for source_name, url in FEEDS:
        try:
            feed = feedparser.parse(url)
            entries = getattr(feed, "entries", [])[:MAX_PER_SOURCE]
            for e in entries:
                title = strip_html(getattr(e, "title", ""))
                link = getattr(e, "link", "")
                desc = strip_html(getattr(e, "summary", "") or getattr(e, "description", ""))
                pub = entry_datetime(e)
                img = get_entry_image(e)

                if not title or not link:
                    continue

                all_new.append({
                    "source": source_name,
                    "title": title,
                    "link": link,
                    "published": pub,
                    "image": img,
                    "summary_raw": desc[:600],  # léger
                    "ai_summary": None,
                    "credit": source_name,
                })
        except Exception as ex:
            logger.error(f"[FETCH] Erreur source {source_name} : {ex}")

    logger.info(f"[FETCH] {len(all_new)} articles récupérés (avant dédup)")
    all_new = dedup_articles(all_new)
    logger.info(f"[DEDUP] {len(all_new)} articles après dédup")

    # Résumer seulement les 1–2 premiers (token saving)
    to_summarize = all_new[:SUMMARIES_PER_FETCH]
    for art in to_summarize:
        summ = summarize_with_openai_french(art["title"], art.get("summary_raw", ""))
        if summ:
            art["ai_summary"] = summ

    # Fusionner avec l’historique, nouvelles en haut
    # Tri par date desc (nouvelles d’abord), puis sauvegarde cumulée
    all_new_sorted = sorted(all_new, key=lambda a: a["published"], reverse=True)
    save_articles(all_new_sorted)
    logger.info("[SAVE] Articles fusionnés et sauvegardés")

# ------------- ROUTES -------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/articles")
def api_articles():
    return jsonify(load_articles())

# ------------- SCHEDULER & RUN -------------
def start_scheduler():
    sched = BackgroundScheduler(timezone="UTC")
    # exécuter une fois au démarrage + toutes les heures
    sched.add_job(fetch_articles, "interval", minutes=FETCH_INTERVAL_MIN, next_run_time=datetime.now(timezone.utc))
    sched.start()
    return sched

if __name__ == "__main__":
    ensure_files()
    try:
        fetch_articles()  # un premier passage
    except Exception as e:
        logger.error(f"Fetch initial échoué : {e}")
    start_scheduler()
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
