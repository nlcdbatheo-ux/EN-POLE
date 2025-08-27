import os
import feedparser
import httpx
import logging
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)

openai_api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

RSS_FEEDS = [
    "https://www.motorsport.com/rss/news/",
    "https://www.formula1.com/rss/news/latest.html",
    "https://www.skysports.com/rss/12040"
]

ARTICLES = []

# Paramètres de similarité
SIMILARITY_THRESHOLD = 0.85  # Entre 0 et 1

def fetch_articles():
    logging.info("[FETCH] Récupération des articles RSS")
    articles = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            articles.append({
                "title": getattr(entry, "title", ""),
                "summary": getattr(entry, "summary", ""),
                "url": getattr(entry, "link", ""),
                "published": getattr(entry, "published", datetime.utcnow().isoformat())
            })
    logging.info(f"[FETCH] {len(articles)} articles récupérés")
    return articles

def get_embedding(text):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def cosine_similarity(a, b):
    from numpy import dot
    from numpy.linalg import norm
    return dot(a, b) / (norm(a) * norm(b))

def deduplicate_articles(articles):
    logging.info("[DEDUP] Déduplication sémantique")
    unique_articles = []
    embeddings = []

    for article in articles:
        emb = get_embedding(article["title"])
        is_unique = True
        for e in embeddings:
            if cosine_similarity(emb, e) > SIMILARITY_THRESHOLD:
                is_unique = False
                break
        if is_unique:
            embeddings.append(emb)
            unique_articles.append(article)

    logging.info(f"[DEDUP] {len(unique_articles)} articles uniques après déduplication")
    return unique_articles

def rewrite_article(article):
    try:
        prompt = f"Réécris cet article en français clair et concis :\n\nTitre: {article['title']}\nRésumé: {article['summary']}"
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        content = response.choices[0].message.content
        return {
            "title": content.split("\n")[0],
            "summary": "\n".join(content.split("\n")[1:]),
            "url": article["url"],
            "published": article["published"]
        }
    except Exception as e:
        logging.error(f"[OPENAI] Erreur réécriture: {e}")
        return article

def pipeline():
    logging.info("[PIPELINE] Début pipeline")
    articles = fetch_articles()
    unique_articles = deduplicate_articles(articles)
    rewritten_articles = [rewrite_article(a) for a in unique_articles]
    
    global ARTICLES
    ARTICLES = rewritten_articles
    logging.info(f"[PIPELINE] {len(ARTICLES)} articles publiés")

@app.route("/news")
def get_news():
    limit = int(httpx.Request.args.get("limit", 20))
    if not ARTICLES:
        return jsonify({"items": []})
    return jsonify({"items": ARTICLES[:limit]})

scheduler = BackgroundScheduler()
scheduler.add_job(pipeline, "interval", minutes=2)
scheduler.start()

if __name__ == "__main__":
    pipeline()
    app.run(host="0.0.0.0", port=10000)
