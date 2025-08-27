import os
import logging
import feedparser
from flask import Flask, jsonify, render_template
from openai import OpenAI

# Initialisation
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
MAX_ARTICLES_PER_FEED = 2      # on limite à 2 par site
MAX_OPENAI_CALLS = 2           # max 2 résumés OpenAI
OPENAI_MODEL = "gpt-3.5-turbo" # modèle utilisé

# Client OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Flux RSS (ajoute ou modifie selon ton besoin)
RSS_FEEDS = {
    "F1i": "https://www.f1i.fr/feed/",
    "Motorsport": "https://www.motorsport.com/rss/f1/news/",
    "NextgenAuto": "https://motorsport.nextgen-auto.com/rss.xml"
}

def summarize_with_openai(title, content):
    """
    Résume un article avec OpenAI.
    Si erreur → retourne None (fallback utilisé plus tard).
    """
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Tu es un assistant qui résume l’actualité F1 de façon claire et concise."},
                {"role": "user", "content": f"Résumé en 3 phrases max de l’article : {title}\n\n{content}"}
            ],
            max_tokens=180
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Erreur OpenAI : {e}")
        return None

def fetch_articles():
    """
    Récupère et traite les articles RSS.
    - Limite la mémoire en ne gardant que titres + résumé.
    - OpenAI seulement pour 2 articles max.
    """
    articles = []
    openai_calls = 0

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                title = entry.get("title", "Sans titre")
                link = entry.get("link", "")
                content = entry.get("summary", "")

                summary = None
                if openai_calls < MAX_OPENAI_CALLS:
                    summary = summarize_with_openai(title, content)
                    if summary:
                        openai_calls += 1

                if not summary:  # fallback si OpenAI HS
                    summary = f"{title} (article original : {link})"

                articles.append({
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "link": link
                })
        except Exception as e:
            logger.error(f"Erreur lors du parsing {url} : {e}")

    return articles

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/articles")
def api_articles():
    return jsonify(fetch_articles())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Render définit automatiquement PORT
    app.run(host="0.0.0.0", port=port)
