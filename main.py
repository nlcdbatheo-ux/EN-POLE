import os
import json
import logging
from datetime import datetime
import feedparser
import httpx
from flask import Flask, render_template
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------------------
# Configuration
# ---------------------------
STATIC_DIR = "static"
ARTICLES_FILE = os.path.join(STATIC_DIR, "articles.json")
MAX_ARTICLES_PER_FEED = 2  # Limite le nombre d'articles par flux pour économiser mémoire

# Liste de flux RSS F1 (exemple)
RSS_FEEDS = [
    {"url": "https://www.formula1.com/en/latest.rss", "source": "Formula1.com"},
    {"url": "https://www.motorsport.com/rss/f1/news/", "source": "Motorsport.com"},
    {"url": "https://www.f1i.com/feed/", "source": "F1i.com"},
    {"url": "https://feeds.feedburner.com/autosport/f1news", "source": "Autosport"},
    {"url": "https://www.crash.net/rss/f1", "source": "Crash.net"}
]

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("en-pole")

# Flask
app = Flask(__name__)

# ---------------------------
# Création dossiers/fichiers
# ---------------------------
def ensure_files():
    os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)
    if not os.path.exists(ARTICLES_FILE):
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

ensure_files()

# ---------------------------
# Lecture / écriture JSON
# ---------------------------
def load_articles():
    with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_articles(articles):
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

# ---------------------------
# Récupération RSS
# ---------------------------
def fetch_articles():
    logger.info("[FETCH] Début récupération RSS")
    all_articles = load_articles()
    new_articles = []

    for feed in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed["url"])
            entries = parsed.entries[:MAX_ARTICLES_PER_FEED]
            for entry in entries:
                article = {
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", str(datetime.utcnow())),
                    "source": feed["source"]
                }
                if article not in all_articles and article not in new_articles:
                    new_articles.append(article)
        except Exception as e:
            logger.error(f"[FETCH] Erreur flux {feed['url']}: {e}")

    # Ajouter en haut
    all_articles = new_articles + all_articles
    save_articles(all_articles)
    logger.info(f"[SAVE] {len(new_articles)} nouveaux articles sauvegardés")

# ---------------------------
# Routes Flask
# ---------------------------
@app.route("/")
def index():
    articles = load_articles()
    return render_template("index.html", articles=articles)

# ---------------------------
# Scheduler
# ---------------------------
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_articles, "interval", hours=1)
scheduler.start()

# ---------------------------
# Démarrage Flask
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
