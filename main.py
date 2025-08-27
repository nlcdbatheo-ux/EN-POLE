import feedparser
import logging
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
import time
import threading
import openai
import os

# Configuration
SOURCES = [
    "https://www.motorsport.com/rss/news/",
    "https://www.formula1.com/en/latest.rss",
    "https://www.skysports.com/rss/12040"
]
CHECK_INTERVAL = 600  # 10 minutes
openai.api_key = os.environ.get("OPENAI_API_KEY")  # tu mets ta clé en variable d'environnement

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

ARTICLES = []

def fetch_articles():
    articles = []
    for url in SOURCES:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            article = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", datetime.utcnow().isoformat())
            }
            articles.append(article)
    logging.info(f"[FETCH] {len(articles)} articles récupérés")
    return articles

def deduplicate_articles(articles):
    seen_titles = set()
    unique_articles = []
    for article in articles:
        title_lower = article["title"].lower()
        if title_lower not in seen_titles:
            seen_titles.add(title_lower)
            unique_articles.append(article)
    logging.info(f"[DEDUP] {len(unique_articles)} articles uniques après déduplication")
    return unique_articles

def rewrite_articles_openai(articles):
    rewritten = []
    for article in articles:
        try:
            prompt = f"Réécris ce texte en français de manière claire et concise:\n{article['title']}"
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100
            )
            new_title = response['choices'][0]['message']['content'].strip()
            article['title'] = new_title
        except Exception as e:
            logging.warning(f"[OPENAI] Échec réécriture: {e}")
        rewritten.append(article)
    return rewritten

def pipeline():
    global ARTICLES
    logging.info("[PIPELINE] Début pipeline")
    articles = fetch_articles()
    articles = deduplicate_articles(articles)
    articles = rewrite_articles_openai(articles)
    ARTICLES = articles
    logging.info(f"[PIPELINE] {len(ARTICLES)} articles publiés")

def scheduler():
    while True:
        pipeline()
        time.sleep(CHECK_INTERVAL)

@app.route("/news", methods=["GET"])
def get_news():
    return jsonify({"items": ARTICLES})

if __name__ == "__main__":
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
