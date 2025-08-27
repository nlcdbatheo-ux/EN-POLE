import os
import json
import logging
import feedparser
from flask import Flask, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import openai

# --- Configuration logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("en-pole")

# --- Configuration Flask ---
app = Flask(__name__)

# --- Directories & files ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
ARTICLES_FILE = os.path.join(STATIC_DIR, "articles.json")

# --- RSS feeds ---
RSS_FEEDS = [
    "https://www.formula1.com/en/latest.rss",
    "https://feeds.bbci.co.uk/sport/formula1/rss.xml",
    "https://www.motorsport.com/rss/f1/news/",
    "https://www.crash.net/rss/formula1/news",
    "https://www.racefans.net/feed/"
]

# --- OpenAI configuration ---
openai.api_key = os.environ.get("OPENAI_API_KEY")

# --- Helpers ---
def ensure_files():
    os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)
    if not os.path.exists(ARTICLES_FILE):
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def load_articles():
    if os.path.exists(ARTICLES_FILE):
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_articles(articles):
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

def summarize_article(title, summary):
    try:
        prompt = f"Résume ce texte de manière concise en français:\nTitre: {title}\nRésumé: {summary}"
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        logger.error(f"Erreur OpenAI : {e}")
        return f"{title} - {summary} (source originale)"

def fetch_articles():
    logger.info("[FETCH] Début récupération RSS")
    articles = load_articles()
    new_articles = []

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:2]:  # Limiter à 2 articles par site pour optimiser mémoire
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")
            author = entry.get("author", "Source inconnue")

            # Détection simple de doublons par titre
            if any(a['title'] == title for a in articles + new_articles):
                continue

            summary_fr = summarize_article(title, summary)
            new_articles.append({
                "title": title,
                "summary": summary_fr,
                "link": link,
                "author": author
            })

    if new_articles:
        # On ajoute les nouveaux articles au début
        articles = new_articles + articles
        save_articles(articles)
        logger.info(f"[SAVE] {len(new_articles)} articles fusionnés et sauvegardés")

# --- Routes Flask ---
@app.route('/')
def home():
    articles = load_articles()
    return render_template("index.html", articles=articles)

@app.route('/articles.json')
def get_articles():
    return jsonify(load_articles())

# --- Scheduler ---
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_articles, 'interval', hours=1)
scheduler.start()

# --- Initial setup ---
ensure_files()
fetch_articles()

# --- Lancement Flask ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
