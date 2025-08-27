import os
import json
import logging
import feedparser
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from dateutil import parser as date_parser
from openai import OpenAI

# Config logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Init Flask
app = Flask(__name__)
CORS(app)

# Init OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Données en mémoire
ARTICLES = []
GROUPED = []

# ---- FETCH RSS ----
FEEDS = [
    "https://www.francetvinfo.fr/titres.rss",
    "https://www.lemonde.fr/rss/une.xml",
]

def fetch_articles():
    global ARTICLES
    articles = []
    for url in FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            articles.append({
                "title": getattr(entry, "title", "Sans titre"),
                "link": getattr(entry, "link", ""),
                "published": getattr(entry, "published", datetime.now(timezone.utc).isoformat())
            })
    ARTICLES = articles
    logger.info(f"[FETCH] {len(articles)} articles récupérés.")

# ---- GROUPING ----
def group_articles():
    global GROUPED
    if not ARTICLES:
        return

    titles = [a["title"] for a in ARTICLES]
    prompt = {
        "instruction": "Regroupe ces articles en 3 à 5 thèmes. Réponds uniquement en JSON valide.",
        "articles": titles
    }

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es un assistant qui renvoie uniquement du JSON."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}
            ],
            response_format={"type": "json_object"}  # ⬅️ FORCE JSON
        )

        raw = resp.choices[0].message.content
        logger.info(f"[OPENAI RAW] {raw}")

        data = json.loads(raw)  # Parse strict JSON
        GROUPED = data.get("themes", [])
        logger.info(f"[GROUPING] {len(GROUPED)} thèmes trouvés.")

    except Exception as e:
        logger.error(f"[GROUPING] Erreur parsing JSON GPT: {e}")
        GROUPED = []

# ---- PIPELINE ----
def pipeline():
    fetch_articles()
    group_articles()
    logger.info(f"[PIPELINE] {len(GROUPED)} actus publiées.")

# Scheduler (toutes les 10 min)
scheduler = BackgroundScheduler()
scheduler.add_job(pipeline, "interval", minutes=10)
scheduler.start()

# ---- ROUTES ----
@app.route("/")
def home():
    return jsonify({"status": "ok", "articles": len(ARTICLES), "grouped": len(GROUPED)})

@app.route("/news")
def get_news():
    return jsonify(GROUPED)

# Lancer une première fois
pipeline()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
