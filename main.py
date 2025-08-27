import os
import json
import logging
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
import feedparser
import httpx
from apscheduler.schedulers.background import BackgroundScheduler

# Config
RSS_FEEDS = [
    "https://www.formula1.com/en/latest/rss/news.rss",
    "https://www.motorsport.com/rss/news/",
    "https://www.skysports.com/rss/12040",
    "https://www.autosport.com/rss/news/",
    "https://www.fia.com/news/feed"
]
MAX_ARTICLES = 20

# Logging
logging.basicConfig(level=logging.INFO)

# Flask app
app = Flask(__name__)
CORS(app)

# Stockage en mémoire
news_items = []

# Scheduler
scheduler = BackgroundScheduler()

# Récupère la clé OpenAI depuis les variables d'environnement
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Clé OpenAI manquante ! Mets OPENAI_API_KEY dans tes variables d'environnement")

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

def fetch_articles():
    logging.info("[FETCH] Récupération des articles RSS")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:MAX_ARTICLES]:
                articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "published": getattr(entry, "published", datetime.utcnow().isoformat()),
                    "source": feed_url
                })
        except Exception as e:
            logging.error(f"[FETCH] Erreur récupération {feed_url}: {e}")
    logging.info(f"[FETCH] {len(articles)} articles récupérés")
    return articles

def deduplicate_articles(articles):
    seen_titles = set()
    unique_articles = []
    for a in articles:
        t = a['title'].lower()
        if t not in seen_titles:
            seen_titles.add(t)
            unique_articles.append(a)
    return unique_articles

def rewrite_article(article):
    """
    Appelle OpenAI pour réécrire l'article en français.
    """
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "Réécris l'article en français de façon claire et synthétique."},
            {"role": "user", "content": f"Titre: {article['title']}\nRésumé: {article['summary']}"}
        ],
        "temperature": 0.7,
        "max_tokens": 300
    }
    try:
        response = httpx.post("https://api.openai.com/v1/chat/completions", headers=HEADERS, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content']
        return {
            "title": article['title'],
            "summary": content,
            "url": article['url'],
            "published_at": article['published'],
            "sources": [article['source']]
        }
    except Exception as e:
        logging.error(f"[OPENAI] Erreur réécriture: {e}")
        return None

def pipeline():
    logging.info("[PIPELINE] Début pipeline")
    articles = fetch_articles()
    unique_articles = deduplicate_articles(articles)
    rewritten = []
    for article in unique_articles:
        rewritten_article = rewrite_article(article)
        if rewritten_article:
            rewritten.append(rewritten_article)
    global news_items
    news_items = rewritten[:MAX_ARTICLES]
    logging.info(f"[PIPELINE] {len(news_items)} articles publiés")

# Flask routes
@app.route("/news")
def get_news():
    return jsonify({"items": news_items})

# Scheduler start
scheduler.add_job(pipeline, 'interval', minutes=5)
scheduler.start()

if __name__ == "__main__":
    pipeline()  # Lance pipeline au démarrage
    app.run(host="0.0.0.0", port=10000)

