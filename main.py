import os
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify
from flask_cors import CORS
import feedparser
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

RSS_FEEDS = [
    "https://www.example.com/rss",
    # ajoute tes flux RSS ici
]

articles_db = []

def fetch_articles():
    logging.info("[FETCH] Récupération des articles RSS")
    articles = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            articles.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", datetime.now(timezone.utc).isoformat())
            })
    logging.info(f"[FETCH] {len(articles)} articles récupérés")
    return articles

def get_embedding(text):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def deduplicate_articles(articles):
    logging.info("[DEDUP] Déduplication sémantique")
    if not articles:
        return []

    titles = [a["title"] for a in articles]
    embeddings = [get_embedding(t) for t in titles]

    unique_articles = []
    added_embeddings = []

    for article, emb in zip(articles, embeddings):
        if added_embeddings:
            sim = cosine_similarity([emb], added_embeddings)[0]
            if any(s > 0.85 for s in sim):
                continue
        unique_articles.append(article)
        added_embeddings.append(emb)
    logging.info(f"[DEDUP] {len(unique_articles)} articles uniques après déduplication")
    return unique_articles

def rewrite_titles(articles):
    logging.info("[OPENAI] Réécriture des titres")
    for article in articles:
        try:
            prompt = f"Réécris ce titre de manière claire et concise, en gardant le sens:\n\n{article['title']}"
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5
            )
            article['title_rewrite'] = response.choices[0].message.content.strip()
        except Exception as e:
            logging.warning(f"[OPENAI] Échec réécriture: {e}")
            article['title_rewrite'] = article['title']
    return articles

def pipeline():
    logging.info("[PIPELINE] Début pipeline")
    articles = fetch_articles()
    articles = deduplicate_articles(articles)
    articles = rewrite_titles(articles)
    global articles_db
    articles_db = articles
    logging.info("[PIPELINE] Articles publiés")

scheduler = BackgroundScheduler()
scheduler.add_job(pipeline, 'interval', minutes=10)  # toutes les 10 minutes
scheduler.start()

@app.route("/news", methods=["GET"])
def get_news():
    return jsonify(articles_db)

if __name__ == "__main__":
    pipeline()
    app.run(host="0.0.0.0", port=10000)
