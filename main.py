from flask import Flask, jsonify, render_template
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from datetime import datetime
import pytz
from openai import OpenAI
import logging

# --- Configuration ---
RSS_FEEDS = [
    "https://www.example.com/rss",
    "https://www.anotherexample.com/rss"
]
OPENAI_API_KEY = "TON_OPENAI_API_KEY"
FETCH_INTERVAL_MINUTES = 60  # Toutes les heures

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=OPENAI_API_KEY)
articles = []

# --- Fonction de récupération RSS ---
def fetch_articles():
    global articles
    logging.info("[FETCH] Début récupération RSS")
    fetched = []
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            fetched.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", datetime.utcnow().isoformat())
            })
    logging.info(f"[FETCH] {len(fetched)} articles récupérés")
    articles = deduplicate_articles(fetched)

# --- Déduplication sémantique ---
def deduplicate_articles(article_list):
    logging.info("[DEDUP] Début déduplication sémantique")
    unique = []
    seen_embeddings = []
    
    for article in article_list:
        emb = get_embedding(article["title"])
        # On vérifie la similarité avec les articles déjà vus
        if not any(similarity(emb, e) > 0.85 for e in seen_embeddings):
            unique.append(article)
            seen_embeddings.append(emb)
    
    logging.info(f"[DEDUP] {len(unique)} articles uniques après déduplication")
    return unique

# --- Création embeddings avec OpenAI ---
def get_embedding(text):
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logging.error(f"[OPENAI] Erreur embedding : {e}")
        return []

# --- Calcul de similarité cosinus ---
def similarity(vec1, vec2):
    if not vec1 or not vec2:
        return 0
    dot = sum(a*b for a, b in zip(vec1, vec2))
    norm1 = sum(a*a for a in vec1) ** 0.5
    norm2 = sum(b*b for b in vec2) ** 0.5
    return dot / (norm1 * norm2) if norm1 and norm2 else 0

# --- Routes Flask ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/news")
def get_news():
    return jsonify(articles)

# --- Scheduler pour fetch automatique ---
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_articles, "interval", minutes=FETCH_INTERVAL_MINUTES)
scheduler.start()

# --- Premier fetch au démarrage ---
fetch_articles()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
