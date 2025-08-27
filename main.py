# main.py
from flask import Flask, render_template
import feedparser
import openai
import logging

app = Flask(__name__)

# --- CONFIGURATION OPENAI ---
# La clé API doit être définie dans Render via les variables d'environnement
# openai.api_key = os.getenv("OPENAI_API_KEY")

# --- SITES RSS F1 ---
RSS_FEEDS = [
    {"url": "https://www.formula1.com/en/latest.rss", "source": "Formula1.com"},
    {"url": "https://www.motorsport.com/rss/f1/news/", "source": "Motorsport.com"},
    {"url": "https://www.autosport.com/rss/f1/", "source": "Autosport.com"},
    {"url": "https://www.f1i.com/feed/", "source": "F1i.com"},
    {"url": "https://www.crash.net/f1/rss", "source": "Crash.net"}
]

# --- FONCTION DE RÉCUPÉRATION DES ARTICLES ---
def fetch_articles():
    articles = []
    for feed in RSS_FEEDS:
        try:
            parsed_feed = feedparser.parse(feed["url"])
            for entry in parsed_feed.entries[:5]:  # max 5 articles par feed
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.get("summary", ""),
                    "source": feed["source"]
                })
        except Exception as e:
            logging.error(f"Erreur récupération RSS {feed['source']}: {e}")
    return articles

# --- FONCTION DE TRAITEMENT OPENAI ---
def process_with_openai(article_text):
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Tu es un assistant de résumé et traduction."},
                {"role": "user", "content": article_text}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Erreur OpenAI : {e}")
        return None  # retour None si problème OpenAI

# --- ROUTE FLASK ---
@app.route("/")
def home():
    articles = fetch_articles()
    final_articles = []

    for article in articles:
        texte_final = process_with_openai(article["summary"])
        if texte_final is None:
            # Fallback : on affiche le texte original avec citation de la source
            texte_final = f"{article['summary']}\n(Source : {article['source']})"
        final_articles.append({
            "title": article["title"],
            "link": article["link"],
            "content": texte_final
        })

    return render_template("index.html", articles=final_articles)

if __name__ == "__main__":
    # Déploiement sur Render : le port est fourni par l'environnement
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

