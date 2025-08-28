import os
import json
import logging
from datetime import datetime
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

# OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Flask
app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------------- RSS FEEDS ---------------- #
RSS_FEEDS = [
    "https://www.formula1.com/rss",                   # Formula1.com
    "https://www.motorsport.com/rss/f1/news/",       # Motorsport F1
    "https://www.autosport.com/f1/rss",              # Autosport F1
    "https://www.crash.net/f1/rss/news",             # Crash.net F1
    "https://www.f1i.com/feed/",                     # F1i.com
    "https://www.f1fanatic.co.uk/feed/",             # F1Fanatic
    "https://www.racefans.net/feed/",                # RaceFans
    "https://www.grandprix247.com/feed/",            # GrandPrix247
    "https://www.thecheckeredflag.co.uk/feed/",      # The Checkered Flag
    "https://www.paddocktalk.com/rss/f1"             # PaddockTalk F1
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

# ---------------- OPENAI ---------------- #
def summarize_and_translate(title, content):
    """Résumé + traduction FR via OpenAI en une seule phrase. Fallback si erreur."""
    try:
        prompt = f"""
        Voici un article en anglais sur la F1 :
        Titre : {title}
        Contenu : {content}

        1. Résume-le en **une seule phrase** en français.
        2. Traduis le titre en français.
        """
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.choices[0].message.content.strip()

        # Séparer titre et résumé si possible
        if "\n" in result:
            lines = result.split("\n")
            fr_title = lines[0].replace("Titre:", "").strip()
            summary = " ".join(lines[1:]).replace("Résumé:", "").strip()
        else:
            fr_title, summary = title, result

        return fr_title, summary
    except Exception as e:
        logger.error(f"[OpenAI] Erreur traduction : {e}")
        return title, content[:200] + "..."

# ---------------- LOGIQUE ---------------- #
def fetch_articles():
    logger.info("[FETCH] Début récupération RSS")
    ensure_files()
    existing = load_articles()

    new_articles = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:5]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            date = entry.get("published", datetime.utcnow().isoformat())

            # Vérifier similarité
            found_similar = False
            for art in existing:
                if similar(title, art["title"]) > 0.7:
                    if link not in art["sources"]:
                        art["sources"].append(link)
                    found_similar = True
                    break

            if not found_similar:
                # Nouveau -> résumer/traduire
                fr_title, fr_summary = summarize_and_translate(title, summary)
                new_articles.append({
                    "title": fr_title,
                    "summary": fr_summary,  # seulement le résumé en français (1 phrase)
                    "date": date,
                    "sources": [link],
                })

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
