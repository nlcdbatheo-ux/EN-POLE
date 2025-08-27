import os
import logging
import json
from datetime import datetime
from flask import Flask, jsonify
import feedparser
from openai import OpenAI

# -------------------- CONFIG --------------------
NEWS_SOURCES = [
    ("Motorsport", "https://www.motorsport.com/rss/f1/news/"),
    ("F1.com", "https://www.formula1.com/rss/news/latest"),
    ("Autosport", "https://www.autosport.com/rss/f1/news/")
]

CONFIRMATION_MIN_SOURCES = 2
MAX_ITEMS_PER_SOURCE = 10

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY manquant – définis-le dans Render !")

client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------- FLASK --------------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# -------------------- ETAPE 1 : FETCH --------------------
def fetch_rss():
    """Récupère les articles depuis les flux RSS."""
    all_items = []
    for source_name, url in NEWS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
                item = {
                    "source": source_name,
                    "title": entry.title,
                    "summary": getattr(entry, "summary", ""),
                    "published": getattr(entry, "published", datetime.utcnow().isoformat())
                }
                all_items.append(item)
        except Exception as e:
            logging.error(f"[FETCH] Erreur sur {source_name}: {e}")
    logging.info(f"[FETCH] {len(all_items)} articles récupérés.")
    return all_items

# -------------------- ETAPE 2 : GROUPEMENT --------------------
def group_by_similarity(items):
    """Utilise GPT pour regrouper les articles similaires."""
    prompt = """
    Voici une liste d'articles provenant de plusieurs sites F1.
    Regroupe ceux qui parlent du même événement, même si la formulation diffère.
    Réponds uniquement en JSON, format:
    [
      {
        "event": "Résumé court de l'événement",
        "sources": ["NomSite1", "NomSite2"],
        "titles": ["titre1", "titre2"]
      }
    ]
    Ne garde que les événements confirmés par au moins 2 sources.
    """

    articles_text = "\n".join([f"- ({a['source']}) {a['title']}" for a in items])

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un assistant qui regroupe des articles similaires."},
            {"role": "user", "content": prompt + "\n" + articles_text}
        ],
        temperature=0
    )

    try:
        groups = json.loads(response.choices[0].message.content)
        logging.info(f"[GROUPING] {len(groups)} groupes détectés par GPT.")
    except Exception as e:
        logging.error(f"[GROUPING] Erreur parsing JSON GPT: {e}")
        groups = []

    return groups

# -------------------- ETAPE 3 : VALIDATION --------------------
def validate_group(group):
    """Valide qu'un groupe est bien confirmé par assez de sources."""
    if len(group.get("sources", [])) < CONFIRMATION_MIN_SOURCES:
        logging.info(f"[VALIDATION] Groupe rejeté (trop peu de sources): {group.get('event')}")
        return False
    logging.info(f"[VALIDATION] Groupe validé: {group.get('event')} ({len(group['sources'])} sources)")
    return True

# -------------------- ETAPE 4 : REFORMULATION --------------------
def reformulate_event(event):
    """Demande à GPT de rédiger une brève neutre et concise."""
    prompt = f"""
    Rédige une brève neutre et concise à partir de ces titres d'articles :
    {event['titles']}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un journaliste sportif, concis et factuel."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5
    )

    text = response.choices[0].message.content.strip()
    logging.info(f"[REFORMULATION] Brève générée: {text[:60]}...")
    return text

# -------------------- ETAPE 5 : PIPELINE COMPLET --------------------
def pipeline():
    items = fetch_rss()
    groups = group_by_similarity(items)
    results = []
    for g in groups:
        if not validate_group(g):
            continue
        summary = reformulate_event(g)
        results.append({
            "summary": summary,
            "sources": g["sources"]
        })
    logging.info(f"[PIPELINE] {len(results)} actus publiées.")
    return results

# -------------------- ROUTES --------------------
@app.route("/")
def home():
    return {"message": "Service de news F1 en ligne."}

@app.route("/news")
def news():
    return jsonify(pipeline())

@app.route("/debug")
def debug():
    """Montre les regroupements bruts avant reformulation."""
    items = fetch_rss()
    groups = group_by_similarity(items)
    return jsonify(groups)

# -------------------- MAIN --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
