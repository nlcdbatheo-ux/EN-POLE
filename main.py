from flask import Flask, render_template, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from datetime import datetime
import openai
import os

app = Flask(__name__)
CORS(app)

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Stockage des articles
articles = []

RSS_FEEDS = [
    "https://www.formula1.com/en/latest.rss"
]

def rewrite_article(content):
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional F1 news editor."},
                {"role": "user", "content": content}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[OPENAI] Échec réécriture: {e}")
        return content

def fetch_articles():
    global articles
    all_articles = []
    print("[FETCH] Début récupération RSS")
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            all_articles.append({
                "title": entry.get("title"),
                "link": entry.get("link"),
                "published": entry.get("published", datetime.utcnow().isoformat())
            })
    print(f"[FETCH] {len(all_articles)} articles récupérés")
    
    # Déduplication simple
    unique = {}
    for a in all_articles:
        if a["link"] not in unique:
            unique[a["link"]] = a
    articles = list(unique.values())
    print(f"[DEDUP] {len(articles)} articles uniques après déduplication")

# Scheduler pour récupérer toutes les heures
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_articles, 'interval', hours=1)
scheduler.start()

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/news')
def get_news():
    global articles
    # Réécriture avec OpenAI
    rewritten = []
    for a in articles:
        a_copy = a.copy()
        a_copy["title"] = rewrite_article(a["title"])
        rewritten.append(a_copy)
    return jsonify(rewritten)

if __name__ == '__main__':
    fetch_articles()
    app.run(host='0.0.0.0', port=10000)
