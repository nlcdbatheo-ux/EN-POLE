import feedparser
from flask import Flask, render_template
from flask_cors import CORS
import openai
import logging

# Configuration de l'API OpenAI
openai.api_key = "TA_CLE_OPENAI_ICI"

# Configuration du Flask
app = Flask(__name__)
CORS(app)

# Liste des flux RSS F1
rss_feeds = [
    "https://www.formula1.com/rss/news/latest.rss",
    "https://www.autosport.com/rss/f1-news",
    "https://www.motorsport.com/rss/f1/",
    "https://www.crash.net/rss/f1",
    "https://www.f1i.com/feed/"
]

def fetch_articles():
    articles = []
    for feed in rss_feeds:
        d = feedparser.parse(feed)
        for entry in d.entries:
            articles.append(entry.title + " " + entry.summary)
    return articles

def deduplicate_articles(articles):
    # Envoi à OpenAI pour détecter doublons
    if not articles:
        return []

    prompt = "Voici plusieurs articles sur la Formule 1. Regroupe ceux qui parlent de la même information, même si les phrases sont différentes, et renvoie uniquement les titres uniques :\n\n"
    for a in articles:
        prompt += "- " + a + "\n"

    try:
        response = openai.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "Tu es un assistant qui simplifie et déduit les doublons d'articles."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        content = response.choices[0].message["content"]
        # Séparer par ligne pour récupérer la liste
        unique_articles = [line.strip("- ").strip() for line in content.split("\n") if line.strip()]
        return unique_articles
    except Exception as e:
        logging.error(f"Erreur OpenAI : {e}")
        return articles  # fallback si erreur

@app.route("/")
def index():
    articles = fetch_articles()
    unique_articles = deduplicate_articles(articles)
    return render_template("index.html", articles=unique_articles)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

