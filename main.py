import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
import openai

# ----------------- CONFIG -----------------
STATIC_DIR = "static"
ARTICLES_FILE = os.path.join(STATIC_DIR, "articles.json")
PORT = int(os.environ.get("PORT", 10000))  # Render attribue le port via variable d'environnement

# Clé OpenAI depuis Render
openai.api_key = os.environ.get("OPENAI_API_KEY")

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("en-pole")

# ----------------- INIT -----------------
app = Flask(__name__)
scheduler = BackgroundScheduler()

# ----------------- FONCTIONS -----------------
def ensure_files():
    os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)
    if not os.path.exists(ARTICLES_FILE):
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def traduire_en_francais(texte):
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Tu es un traducteur français précis et naturel."},
                {"role": "user", "content": f"Traduis ce texte en français :\n\n{texte}"}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Erreur OpenAI : %s", e)
        return texte  # Retourne le texte original si OpenAI échoue

def fetch_articles():
    logger.info("[FETCH] Début récupération RSS")
    feeds = [
        {"name": "F1.com", "url": "https://www.formula1.com/en/latest.rss"},
        {"name": "Autosport", "url": "https://www.autosport.com/rss/f1-news"},
        {"name": "Motorsport", "url": "https://www.motorsport.com/rss/f1/"},
        {"name": "ESPN F1", "url": "https://www.espn.com/espn/rss/f1/news"},
        {"name": "Sky Sports F1", "url": "https://www.skysports.com/rss/12040"}
    ]

    articles = []
    for feed in feeds:
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[:2]:  # Limiter à 2 articles par site
                article = {
                    "source": feed["name"],
                    "title": traduire_en_francais(entry.get("title", "")),
                    "summary": traduire_en_francais(entry.get("summary", "")),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", str(datetime.utcnow()))
                }
                articles.append(article)
        except Exception as e:
            logger.error("Erreur récupération %s : %s", feed["name"], e)

    # Déduplication simple
    seen_titles = set()
    unique_articles = []
    for a in articles:
        if a["title"] not in seen_titles:
            seen_titles.add(a["title"])
            unique_articles.append(a)

    # Sauvegarde
    try:
        if os.path.exists(ARTICLES_FILE):
            with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
                saved_articles = json.load(f)
        else:
            saved_articles = []

        # Conserver les anciens articles + nouveaux
        all_articles = unique_articles + saved_articles
        all_articles = all_articles[:50]  # Limiter pour éviter mémoire excessive

        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump(all_articles, f, ensure_ascii=False, indent=2)

        logger.info("[SAVE] Articles fusionnés et sauvegardés")
    except Exception as e:
        logger.error("Erreur sauvegarde articles : %s", e)

# ----------------- ROUTES -----------------
@app.route("/")
def index():
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except Exception:
        articles = []
    return render_template("index.html", articles=articles)

@app.route("/articles.json")
def articles_json():
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except Exception:
        articles = []
    return jsonify(articles)

# ----------------- MAIN -----------------
if __name__ == "__main__":
    ensure_files()
    fetch_articles()
    scheduler.add_job(fetch_articles, 'interval', hours=1)
    scheduler.start()
    app.run(host="0.0.0.0", port=PORT)
