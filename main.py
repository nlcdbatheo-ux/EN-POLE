import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import openai
from datetime import datetime

# ======================
# Flask & CORS
# ======================
app = Flask(__name__)
CORS(app)

# ======================
# OpenAI API Key
# ======================
openai.api_key = os.environ.get("OPENAI_API_KEY")

# ======================
# Données et pipeline
# ======================
ARTICLES = []

def fetch_articles():
    """
    Remplace cette fonction par tes flux RSS ou API réels
    """
    site1 = [
        {"id": 1, "title": "Événement A à Paris", "content": "La mairie organise un festival", "source": "Site1"},
        {"id": 2, "title": "Sport B ce week-end", "content": "Le match aura lieu dimanche", "source": "Site1"}
    ]
    site2 = [
        {"id": 3, "title": "Festival à Paris", "content": "La mairie lance un festival", "source": "Site2"},
        {"id": 4, "title": "Match Sport B", "content": "Dimanche, le match aura lieu", "source": "Site2"}
    ]
    return site1 + site2

def are_articles_similar(content1, content2):
    """
    Utilise OpenAI pour déterminer si deux articles parlent de la même chose
    """
    prompt = f"Est-ce que ces deux textes parlent du même sujet ? Répondre par 'oui' ou 'non'.\n\nTexte 1: {content1}\nTexte 2: {content2}"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5
        )
        answer = response.choices[0].message['content'].strip().lower()
        return "oui" in answer
    except Exception as e:
        print("Erreur OpenAI:", e)
        return False

def pipeline_process():
    """
    Compare tous les articles et marque ceux qui sont similaires
    """
    global ARTICLES
    articles = fetch_articles()
    duplicates = []

    for i, art1 in enumerate(articles):
        for j, art2 in enumerate(articles):
            if i >= j:
                continue
            if are_articles_similar(art1['content'], art2['content']):
                duplicates.append({
                    "article1": art1,
                    "article2": art2
                })

    ARTICLES = articles
    print(f"[PIPELINE] {len(articles)} articles traités, {len(duplicates)} doublons détectés")
    return {"articles": articles, "duplicates": duplicates}

# ======================
# Routes Flask
# ======================
@app.route("/news")
def news():
    limit = int(request.args.get("limit", 20))
    return jsonify(ARTICLES[:limit])

@app.route("/run_pipeline")
def run_pipeline():
    result = pipeline_process()
    return jsonify(result)

# ======================
# Point d'entrée principal
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
