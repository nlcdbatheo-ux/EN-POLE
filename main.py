import os
import logging
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import feedparser
import openai

# Configuration OpenAI via variable d'environnement
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

# Liste de flux RSS Formule 1
RSS_FEEDS = [
    "https://www.formula1.com/en/latest/rss.xml",
    "https://www.f1i.com/feed/",
    "https://www.motorsport.com/rss/f1/news/",
    "https://www.autosport.com/rss/f1/",
    "https://www.crash.net/rss/f1/news"
]

def summarize_article(title, content):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Tu es un assistant qui résume les articles de Formule 1."},
                {"role": "user", "content": f"Résume cet article et traduis-le en français si nécessaire :\nTitre : {title}\nContenu : {content}"}
            ],
            max_tokens=150
        )
        return response.choices[0].message['content']
    except Exception as e:
        logging.error(f"Erreur OpenAI : {e}")
        # Renvoie au moins le titre original si OpenAI échoue
        return f"[Résumé indisponible] {title}"

@app.route("/")
def home():
    articles = []

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:2]:  # max 2 articles par flux pour limiter
            summary = summarize_article(entry.get('title', ''), entry.get('summary', ''))
            articles.append({
                "title": entry.get('title', ''),
                "link": entry.get('link', ''),
                "summary": summary
            })

    return render_template("index.html", articles=articles)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
