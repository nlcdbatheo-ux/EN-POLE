import feedparser
import httpx
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from openai import OpenAI

# --- CONFIG ---
API_KEY = "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"
FEEDS = [
    "https://www.formula1.com/en/latest.rss",
    "https://www.motorsport.com/rss/news/",
    "https://www.skysports.com/rss/12040",
    "https://www.autosport.com/rss/f1/news/",
    "https://www.f1i.com/feed/"
]
NEWS_LIMIT = 20

# --- INIT ---
app = Flask(__name__)
CORS(app)
scheduler = BackgroundScheduler()
client = OpenAI(api_key=API_KEY)
articles_cache = []

logging.basicConfig(level=logging.INFO)

# --- UTIL ---
async def fetch_feed(url):
    logging.info(f"[FETCH] {url}")
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries:
        items.append({
            "title": entry.get("title"),
            "summary": entry.get("summary", ""),
            "url": entry.get("link"),
            "published": entry.get("published", datetime.utcnow().isoformat())
        })
    return items

def deduplicate_articles(articles):
    """Regroupe les articles proches sémantiquement via OpenAI embeddings"""
    if not articles:
        return []

    unique_articles = []
    seen_texts = []

    for art in articles:
        text_to_check = art["title"] + " " + art["summary"]
        is_duplicate = False
        for seen in seen_texts:
            # comparaison rapide via simple ratio de similarité avec OpenAI embeddings
            resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=[text_to_check, seen]
            )
            emb1, emb2 = resp.data[0].embedding, resp.data[1].embedding
            # cos similarity
            dot = sum(a*b for a,b in zip(emb1, emb2))
            norm1 = sum(a*a for a in emb1) ** 0.5
            norm2 = sum(b*b for b in emb2) ** 0.5
            similarity = dot / (norm1 * norm2)
            if similarity > 0.85:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_articles.append(art)
            seen_texts.append(text_to_check)
    return unique_articles

def rewrite_article(article):
    """Réécrit le titre et le résumé en français via OpenAI"""
    prompt = (
        f"Réécris cet article de Formule 1 en français, de façon claire et concise :\n\n"
        f"Titre : {article['title']}\nRésumé : {article['summary']}\n\nRéécriture :"
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    rewritten = resp.choices[0].message.content.strip()
    return {
        "title": rewritten.split("\n")[0] if "\n" in rewritten else rewritten,
        "summary": rewritten,
        "url": article["url"],
        "published_at": article["published"],
        "sources": [article["url"].split("/")[2]]
    }

# --- PIPELINE ---
async def pipeline():
    logging.info("[PIPELINE] Récupération des flux")
    all_articles = []
    for feed in FEEDS:
        try:
            articles = await fetch_feed(feed)
            all_articles.extend(articles)
        except Exception as e:
            logging.error(f"Erreur fetch {feed}: {e}")

    logging.info(f"[PIPELINE] {len(all_articles)} articles récupérés")
    unique_articles = deduplicate_articles(all_articles)
    logging.info(f"[PIPELINE] {len(unique_articles)} articles après dé-duplication")

    rewritten_articles = []
    for art in unique_articles[:NEWS_LIMIT]:
        try:
            rewritten = rewrite_article(art)
            rewritten_articles.append(rewritten)
        except Exception as e:
            logging.error(f"Erreur réécriture article {art['url']}: {e}")

    global articles_cache
    articles_cache = rewritten_articles
    logging.info(f"[PIPELINE] {len(articles_cache)} articles prêts à être publiés")

# --- ROUTES ---
@app.route("/news")
def news():
    if not articles_cache:
        return jsonify({"items": []})
    return jsonify({"items": articles_cache})

# --- SCHEDULER ---
scheduler.add_job(lambda: httpx.run(pipeline()), "interval", minutes=10)
scheduler.start()

# --- START ---
if __name__ == "__main__":
    import asyncio
    asyncio.run(pipeline())
    app.run(host="0.0.0.0", port=10000)
