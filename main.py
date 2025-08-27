import feedparser
import logging
from flask import Flask, render_template
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import openai
from difflib import SequenceMatcher

# Configuration OpenAI
openai.api_key = "TON_CLE_OPENAI_ICI"

# Initialisation Flask
app = Flask(__name__)
CORS(app)

# Liste des flux RSS F1 populaires
RSS_FEEDS = [
    "https://www.formula1.com/en/latest.rss",
    "https://www.motorsport.com/rss/f1/news/",
    "https://www.f1i.com/feed/",
    "https://www.racingnews365.com/feed",
    "https://feeds.feedburner.com/F1Fanatic"
]

# Stockage des articles
articles_store = []

# Logger
logging.basicConfig(level=logging.INFO)

# Fonction pour déduplication par similarité
def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

# Fonction pour réécrire le texte via OpenAI
def rewrite_text(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "Tu es un assistant qui résume et réécrit les articles de Formule 1 en français."},
                {"role": "user", "content": f"Réécris ce texte de manière claire et concise : {text}"}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Erreur OpenAI : {e}")
        return text

# Fonction pour récupérer les articles
def fetch_articles():
    global articles_store
    logging.info("[FETCH] Début récupération RSS")
    new_articles = []

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            new_articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": getattr(entry, "published", ""),
                "summary": getattr(entry, "summary", "")
            })

    logging.info(f"[FETCH] {len(new_articles)} articles récupérés")

    # Déduplication
    unique_articles = []
    for article in new_articles:
        duplicate = False
        for existing in unique_articles:
            if similar(article["title"], existing["title"]) > 0.85:
                duplicate = True
                break
        if not duplicate:
            unique_articles.append(article)

    logging.info(f"[DEDUP] {len(unique_articles)} articles uniques après déduplication")

    # Réécriture des résumés
    for article in unique_articles:
        article["summary"] = rewrite_text(article["summary"])

    articles_store = unique_articles

# Scheduler pour lancer toutes les heures
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_articles, 'interval', hours=1)
scheduler.start()

# Route principale
@app.route("/")
def home():
    return render_template("index.html", articles=articles_store)

if __name__ == "__main__":
    fetch_articles()
    app.run(host="0.0.0.0", port=10000)
