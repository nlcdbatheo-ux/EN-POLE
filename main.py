import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from datetime import datetime
import dateutil.parser
# import openai  # Décommenter si tu utilises OpenAI

# ======================
# Configuration du Flask
# ======================
app = Flask(__name__)
CORS(app)  # Autoriser les requêtes cross-origin

# ======================
# Pipeline / ingestion
# ======================
# Exemple minimal : remplacer par ton code réel
ARTICLES = []

def fetch_articles(limit=20):
    """
    Fonction pour récupérer les articles.
    Remplace ceci par ton code réel d'ingestion.
    """
    return [{"id": i, "title": f"Article {i}", "published": datetime.now().isoformat()} for i in range(1, limit+1)]

def pipeline_process():
    """
    Traitement du pipeline : ingestion et grouping
    """
    global ARTICLES
    print("[PIPELINE] Démarrage…")
    articles = fetch_articles(60)  # Exemple : récupérer 60 articles
    ARTICLES = articles  # Met à jour la liste globale
    print(f"[PIPELINE] {len(articles)} articles bruts")
    print(f"[PIPELINE] {len(articles)} groupes candidats")
    print(f"[SCHEDULED] Stats: {{'fetched': {len(articles)}, 'groups': {len(articles)}, 'published': 0}}")
    return articles

# ======================
# Scheduler (optionnel)
# ======================
scheduler = BackgroundScheduler()
# Décommenter pour exécuter le pipeline toutes les 5 minutes par exemple
# scheduler.add_job(func=pipeline_process, trigger="interval", minutes=5)
scheduler.start()

# ======================
# Routes Flask
# ======================
@app.route("/news")
def news():
    limit = int(request.args.get("limit", 20))
    # Retourne les derniers articles
    return jsonify(ARTICLES[:limit])

@app.route("/run_pipeline")
def run_pipeline():
    articles = pipeline_process()
    return jsonify({"status": "done", "processed_articles": len(articles)})

# ======================
# Point d'entrée principal
# ======================
if __name__ == "__main__":
    # Render fournit le port via la variable d'environnement PORT
    port = int(os.environ.get("PORT", 10000))  # 10000 par défaut si local
    app.run(host="0.0.0.0", port=port, debug=True)
