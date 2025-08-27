import feedparser
import httpx
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from openai import OpenAI

# --- CONFIG ---
RSS_FEEDS = [
    "https://example.com/rss",
    "https://another.com/rss"
]
OPENAI_API_KEY = "VOTRE_OPENAI_API_KEY"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- CLIENT OPENAI ---
client = OpenAI(api_key=OPENAI_API_KEY)

# --- FLASK ---
app = Flask(__name__)

# --- FONCTIONS ---
def get_embedding(text: str):
    """Retourne l'embedding pour un texte."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def deduplicate_articles(articles):
    """Déduplication sémantique simple."""
    unique_articles = []
    embeddings = []
    for article in articles:
        emb = get_embedding(article["title"])
        # Comparaison simple par similarité cosinus (approx)
        if not any(sum(e1_i * e2_i for e1_i, e2_i in zip(emb, e)) > 0.95 for e in embeddings):
            embeddings.append(emb)
            unique_articles.append(article)
    return unique_articles

def rewrite_article(article):
    """Réécrit le titre pour uniformiser le style."""
    prompt = (
        f"Réécris ce titre pour le rendre uniforme et clair, "
        f"en gardant le sens exact:\n{article['title']}"
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    rewritten_title = response.choices[0].message.content
    article["title"] = rewritten_title
    return article

def fetch_articles():
    """Récupère les articles depuis les flux RSS."""
    articles = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            articles.append({
                "title": entry.get("title"),
                "link": entry.get("link"),
                "published": entry.get("published", datetime.now(timezone.utc).isoformat())
            })
    logging.info(f"[FETCH] {len(articles)} articles récupérés")
    return articles

def pipeline():
    logging.info("[PIPELINE] Début pipeline")
    articles = fetch_articles()
    logging.info("[DEDUP] Déduplication sémantique")
    unique_articles = deduplicate_articles(articles)
    logging.info("[REWRITE] Réécriture des titres")
    rewritten_articles = [rewrite_article(a) for a in unique_articles]
    global latest_articles
    latest_articles = rewritten_articles
    logging.info(f"[PIPELINE] {len(rewritten_articles)} articles publiés")

# --- SCHEDULER ---
scheduler = BackgroundScheduler()
scheduler.add_job(pipeline, 'interval', hours=1)  # exécution toutes les heures
scheduler.start()

# --- ROUTES FLASK ---
latest_articles = []

@app.route("/news")
def news():
    return jsonify(latest_articles)

@app.route("/")
def home():
    return "API en marche. Accédez à /news pour les articles."

# --- MAIN ---
if __name__ == "__main__":
    pipeline()  # lancer une première fois au démarrage
    app.run(host="0.0.0.0", port=10000)
