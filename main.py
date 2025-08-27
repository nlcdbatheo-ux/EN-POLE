import os
import json
import logging
import feedparser
from flask import Flask, jsonify, render_template
import openai

# Config logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API key OpenAI depuis Render (pas besoin de la mettre ici)
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

ARTICLES_FILE = "static/articles.json"

# --- Fonctions utilitaires ---

def save_articles(articles):
    try:
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur sauvegarde articles : {e}")

def load_articles():
    if os.path.exists(ARTICLES_FILE):
        try:
            with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur lecture articles : {e}")
    return []

def fetch_articles():
    feeds = [
        "https://www.formula1.com/rss",  
        "https://www.motorsport.com/rss/f1/news/",
        "https://www.autosport.com/rss/f1/news/",
    ]

    articles = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]:  # limiter à 2 articles par site
                text = entry.get("title", "") + " - " + entry.get("summary", "")
                link = entry.get("link", "")

                try:
                    # Appel OpenAI pour résumer
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "Tu es un journaliste F1. Résume clairement en français."},
                            {"role": "user", "content": text}
                        ],
                        max_tokens=150,
                        temperature=0.7
                    )
                    summary = response.choices[0].message["content"].strip()
                except Exception as e:
                    logger.error(f"Erreur OpenAI : {e}")
                    summary = text  # fallback brut si OpenAI plante

                articles.append({
                    "title": entry.get("title", "Sans titre"),
                    "summary": summary,
                    "link": link,
                    "source": feed.feed.get("title", "Inconnu")
                })

        except Exception as e:
            logger.error(f"Erreur RSS {url}: {e}")

    return articles

# --- Routes Flask ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/articles")
def api_articles():
    articles = load_articles()
    if not articles:  # Si vide, on recharge et on sauvegarde
        articles = fetch_articles()
        save_articles(articles)
    return jsonify(articles)

# --- Lancer serveur ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
