from flask import Flask, render_template
import feedparser
import openai
import os
import logging
from difflib import SequenceMatcher

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Utilisation de la clé OpenAI via les variables d'environnement (Render)
# Pas besoin de mettre la clé ici
openai.api_key = os.getenv("OPENAI_API_KEY")

# Liste des flux RSS F1
RSS_FEEDS = [
    {"name": "F1News", "url": "https://www.formula1.com/rss/news.xml"},
    {"name": "Autosport", "url": "https://www.autosport.com/rss/f1/news/"},
    {"name": "Motorsport", "url": "https://www.motorsport.com/rss/f1/"},
    {"name": "BBC F1", "url": "https://feeds.bbci.co.uk/sport/formula1/rss.xml"},
    {"name": "ESPN F1", "url": "https://www.espn.com/espn/rss/f1/news"}
]

# Fonction pour comparer deux textes et vérifier si ce sont grosso modo les mêmes
def similar(a, b):
    return SequenceMatcher(None, a, b).ratio() > 0.8

# Fonction pour utiliser OpenAI pour résumer/reformuler/traduire
def summarize_article(title, content):
    if not openai.api_key:
        logging.warning("OpenAI non disponible, on retourne l'article original")
        return content
    prompt = f"""
Résumé, reformule et traduis en français si nécessaire cet article de F1.
Si impossible, renvoie l'article original.
Titre: {title}
Contenu: {content}
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        summary = response['choices'][0]['message']['content'].strip()
        return summary
    except Exception as e:
        logging.error(f"Erreur OpenAI : {e}")
        return content

# Récupération et déduplication des articles
def fetch_articles():
    articles = []
    for feed in RSS_FEEDS:
        logging.info(f"[FETCH] Récupération depuis {feed['name']}")
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries:
                article = {
                    "title": entry.get("title", ""),
                    "content": entry.get("summary", entry.get("description", "")),
                    "source": entry.get("link", feed["url"])
                }
                # Déduplication approximative
                if not any(similar(article["content"], a["content"]) for a in articles):
                    article["content"] = summarize_article(article["title"], article["content"])
                    articles.append(article)
        except Exception as e:
            logging.error(f"[ERROR] Erreur récupération {feed['name']}: {e}")
    return articles

@app.route("/")
def home():
    news = fetch_articles()
    return render_template("index.html", news=news)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
