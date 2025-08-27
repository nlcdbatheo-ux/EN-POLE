from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
import feedparser
import openai
import logging

# Config
RSS_FEEDS = [
    "https://www.motorsport.com/rss/news/",
    "https://www.formula1.com/en/latest.rss",
]
OPENAI_API_KEY = "ton_api_key_openai"

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

openai.api_key = OPENAI_API_KEY

def fetch_articles():
    articles = []
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            articles.append({
                "title": getattr(entry, "title", ""),
                "summary": getattr(entry, "summary", ""),
                "url": getattr(entry, "link", ""),
                "published_at": getattr(entry, "published", datetime.now(timezone.utc).isoformat()),
                "source": url
            })
    logging.info(f"[FETCH] {len(articles)} articles récupérés.")
    return articles

def group_articles_with_openai(articles):
    if not articles:
        return []
    try:
        prompt = "Groupe ces actus similaires en thèmes. Renvoie un JSON avec 'items': [{title, summary, url, published_at, sources}]."
        messages = [
            {"role": "system", "content": "Tu es un assistant qui groupe des actus similaires."},
            {"role": "user", "content": prompt + f"\n{articles}"}
        ]
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.3,
            max_tokens=1000
        )
        text = response.choices[0].message.content
        import json
        grouped = json.loads(text)
        logging.info(f"[GROUPING] {len(grouped.get('items', []))} actus groupées.")
        return grouped.get("items", [])
    except Exception as e:
        logging.error(f"[GROUPING] Erreur parsing JSON GPT: {e}")
        return []

@app.route("/news")
def news():
    articles = fetch_articles()
    grouped_items = group_articles_with_openai(articles)
    return jsonify({"items": grouped_items})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
