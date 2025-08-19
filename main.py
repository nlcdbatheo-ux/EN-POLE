import os
import json
import sqlite3
import re
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from flask import Flask, request, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from dateutil import parser as dateparser

# --- OpenAI (nouvelle lib 1.x) ---
from openai import OpenAI
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------------------
# Config & sources
# -------------------------------
# 5 sources RSS (modifiables via ENV si besoin)
DEFAULT_SOURCES = [
    # (nom lisible, url rss)
    ("Motorsport.com", "https://www.motorsport.com/rss/f1/news/"),
    ("Autosport",      "https://www.autosport.com/rss/f1"),
    ("RaceFans",       "https://www.racefans.net/feed/"),
    ("PlanetF1",       "https://www.planetf1.com/feed/"),
    ("Nextgen-Auto",   "https://motorsport.nextgen-auto.com/spip.php?page=backend"),
]

SOURCES: List[Tuple[str, str]] = []
for i, (name, url) in enumerate(DEFAULT_SOURCES, start=1):
    env_url = os.getenv(f"NEWS_SOURCE_{i}_URL")
    SOURCES.append((name, env_url if env_url else url))

FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "10"))
CONFIRMATION_MIN_SOURCES = int(os.getenv("CONFIRMATION_MIN_SOURCES", "2"))
MAX_ITEMS_PER_SOURCE = int(os.getenv("MAX_ITEMS_PER_SOURCE", "30"))  # limite par fetch

DB_PATH = os.getenv("DB_PATH", "news.db")

# -------------------------------
# Flask
# -------------------------------
app = Flask(__name__)
CORS(app)

# -------------------------------
# DB helpers
# -------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_hash TEXT UNIQUE,               -- hash pour éviter les doublons
        title TEXT,
        summary TEXT,
        url TEXT,
        sources_json TEXT,                  -- liste des sources ayant confirmé
        published_at TEXT,                  -- ISO 8601
        created_at TEXT                     -- ISO 8601
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS news_raw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT,
        title TEXT,
        description TEXT,
        url TEXT,
        published_at TEXT,                  -- ISO 8601 si dispo
        fetched_at TEXT                     -- ISO 8601
    )
    """)
    conn.commit()
    conn.close()

# -------------------------------
# Utils
# -------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def to_iso(dt) -> str:
    if isinstance(dt, str):
        try:
            return dateparser.parse(dt).astimezone(timezone.utc).isoformat()
        except Exception:
            return now_iso()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return now_iso()

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9áàâäãåçéèêëíìîïñóòôöõúùûüýÿ'’ -]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

STOPWORDS = set("""
f1 formule formula one grand prix gp le la les de du des d' l' un une au aux en et à a the for of in on
""".split())

def key_from_title(title: str) -> str:
    """
    Crée une clé (hash cheap) à partir du titre pour grouper les articles.
    On retire la ponctuation, les stopwords, et on trie les tokens.
    """
    norm = normalize_text(title)
    tokens = [t for t in norm.split() if t not in STOPWORDS and len(t) > 2]
    # On garde les 8 plus significatifs pour stabiliser la clé
    tokens = sorted(tokens)[:8]
    key = "-".join(tokens)
    # Un mini-hash stable
    return str(abs(hash(key)))  # suffisant pour éviter trop de collisions ici

def similar(a: str, b: str) -> float:
    """
    Similarité grossière par chevauchement de mots (Jaccard).
    """
    sa = set([t for t in normalize_text(a).split() if t not in STOPWORDS])
    sb = set([t for t in normalize_text(b).split() if t not in STOPWORDS])
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / max(1, union)

def merge_groups(items: List[Dict[str, Any]], threshold: float = 0.55):
    """
    Groupe des items similaires (par titre) en "histoires".
    Une histoire = { 'title', 'urls', 'sources', 'published_at', 'raw_text' }
    """
    groups: List[Dict[str, Any]] = []
    for it in items:
        placed = False
        for g in groups:
            if similar(g['title'], it['title']) >= threshold:
                g['items'].append(it)
                # Conserver titre le plus informatif (plus long)
                if len(it['title']) > len(g['title']):
                    g['title'] = it['title']
                placed = True
                break
        if not placed:
            groups.append({
                'title': it['title'],
                'items': [it],
            })

    # Structure finale
    stories = []
    for g in groups:
        srcs = list({i['source'] for i in g['items']})
        urls = [i['url'] for i in g['items'] if i.get('url')]
        # date la plus ancienne (souvent la première publication)
        dates = [i['published_at'] for i in g['items'] if i.get('published_at')]
        pub = min(dates) if dates else now_iso()
        raw_text = "\n\n".join([
            f"[{i['source']}] {i['title']}\n{i.get('description','')}"
            for i in g['items']
        ])
        stories.append({
            'title': g['title'],
            'sources': srcs,
            'urls': urls,
            'published_at': pub,
            'raw_text': raw_text
        })
    return stories

# -------------------------------
# Fetch / Parse RSS
# -------------------------------
def fetch_source(name: str, url: str) -> List[Dict[str, Any]]:
    feed = feedparser.parse(url)
    out = []
    fetched_at = now_iso()
    for i, e in enumerate(feed.entries[:MAX_ITEMS_PER_SOURCE]):
        title = e.get("title", "").strip()
        if not title:
            continue
        link = e.get("link", "")
        summary = e.get("summary", "") or e.get("description", "")
        published = e.get("published") or e.get("updated") or ""
        try:
            if 'published_parsed' in e and e.published_parsed:
                published_dt = datetime.fromtimestamp(time.mktime(e.published_parsed), tz=timezone.utc)
            elif 'updated_parsed' in e and e.updated_parsed:
                published_dt = datetime.fromtimestamp(time.mktime(e.updated_parsed), tz=timezone.utc)
            else:
                published_dt = dateparser.parse(published) if published else datetime.now(timezone.utc)
            published_iso = to_iso(published_dt)
        except Exception:
            published_iso = now_iso()

        out.append({
            "source": name,
            "title": title,
            "description": summary,
            "url": link,
            "published_at": published_iso,
            "fetched_at": fetched_at
        })
    return out

def fetch_all_sources() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for name, url in SOURCES:
        try:
            items.extend(fetch_source(name, url))
        except Exception as e:
            print(f"[WARN] Échec source {name}: {e}")
    return items

# -------------------------------
# OpenAI reformulation
# -------------------------------
REFORMULATE_SYSTEM_PROMPT = (
    "Tu es un journaliste spécialisé en Formule 1 pour le site 'En Pôle Position'. "
    "Tu rédiges en français, ton style est clair, concis et factuel. "
    "Ne publie que ce qui est vérifié par plusieurs sources. "
    "Ajoute si utile le contexte (équipe, pilotes, championnat) mais évite les spéculations."
)

def reformulate_with_openai(title: str, raw_text: str, urls: List[str]) -> str:
    try:
        user_content = (
            f"Titre (provisoire) : {title}\n\n"
            f"Sources multiples (extraits) :\n{raw_text}\n\n"
            f"Liens :\n" + "\n".join(urls[:5]) + "\n\n"
            "Tâche : Rédige un court article (3-5 phrases) qui résume l'information confirmée par au moins deux sources. "
            "Ne mentionne pas OpenAI. Évite les redondances. Si l'info reste incertaine, indique-le."
        )
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": REFORMULATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3,
            max_tokens=280
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] OpenAI reformulation: {e}")
        # fallback: renvoyer quelque chose de propre
        return title

# -------------------------------
# Ingestion pipeline
# -------------------------------
def save_raw_items(raw_items: List[Dict[str, Any]]):
    conn = get_db()
    cur = conn.cursor()
    for it in raw_items:
        cur.execute("""
            INSERT INTO news_raw (source, title, description, url, published_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (it["source"], it["title"], it.get("description",""), it.get("url",""), it.get("published_at",""), it.get("fetched_at","")))
    conn.commit()
    conn.close()

def already_published(key_hash: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM news WHERE key_hash = ? LIMIT 1", (key_hash,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def publish_story(title: str, summary: str, url: str, sources: List[str], published_at: str):
    conn = get_db()
    cur = conn.cursor()
    key_hash = key_from_title(title)
    if already_published(key_hash):
        return False
    cur.execute("""
        INSERT INTO news (key_hash, title, summary, url, sources_json, published_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        key_hash,
        title.strip(),
        summary.strip(),
        url or "",
        json.dumps(sources, ensure_ascii=False),
        published_at,
        now_iso()
    ))
    conn.commit()
    conn.close()
    print(f"[PUBLISHED] {title} ({', '.join(sources)})")
    return True

def run_pipeline() -> Dict[str, Any]:
    """
    1) Fetch RSS de toutes les sources
    2) Regroupe les articles similaires
    3) Garde ceux avec >= CONFIRMATION_MIN_SOURCES
    4) Reformule avec OpenAI
    5) Publie en DB
    """
    print("[PIPELINE] Démarrage…")
    raw = fetch_all_sources()
    print(f"[PIPELINE] {len(raw)} articles bruts")
    if not raw:
        return {"fetched": 0, "groups": 0, "published": 0}

    save_raw_items(raw)

    groups = merge_groups(raw, threshold=0.55)
    print(f"[PIPELINE] {len(groups)} groupes candidats")

    published_count = 0
    for g in groups:
        if len(g["sources"]) >= CONFIRMATION_MIN_SOURCES:
            title = g["title"]
            urls = g["urls"]
            summary = reformulate_with_openai(title, g["raw_text"], urls)
            # URL principale = la première
            main_url = urls[0] if urls else ""
            ok = publish_story(title=title, summary=summary, url=main_url, sources=g["sources"], published_at=g["published_at"])
            if ok:
                published_count += 1

    return {"fetched": len(raw), "groups": len(groups), "published": published_count}

# -------------------------------
# Scheduler
# -------------------------------
scheduler = BackgroundScheduler(daemon=True)

def scheduled_job():
    try:
        stats = run_pipeline()
        print(f"[SCHEDULED] Stats: {stats}")

        # Si aucune actu publiée, on ajoute un message automatique chaque heure pile
        if stats.get("published", 0) == 0:
            now = datetime.now(timezone.utc)
            if now.minute == 0:  # déclenche seulement à HH:00
                publish_story(
                    title="⏳ Pas de nouvelles informations",
                    summary="Pas de nouvelles informations cette heure-ci, revenez plus tard.",
                    url="",
                    sources=["System"],
                    published_at=now_iso()
                )
                print("[INFO] Message 'pas de nouvelles' ajouté.")
    except Exception as e:
        print(f"[SCHEDULED][ERROR] {e}")


# -------------------------------
# API endpoints
# -------------------------------
@app.get("/health")
def health():
    return jsonify({"status": "ok", "time": now_iso()})

@app.get("/news")
def list_news():
    limit = int(request.args.get("limit", "20"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT title, summary, url, sources_json, published_at, created_at
        FROM news
        ORDER BY datetime(published_at) DESC, id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    data = []
    for r in rows:
        data.append({
            "title": r["title"],
            "summary": r["summary"],
            "url": r["url"],
            "sources": json.loads(r["sources_json"] or "[]"),
            "published_at": r["published_at"],
            "created_at": r["created_at"]
        })
    return jsonify({"count": len(data), "items": data})

@app.post("/refresh")
def refresh():
    # Optionnel: sécuriser avec un token simple
    expected = os.getenv("REFRESH_TOKEN")
    provided = request.headers.get("X-Refresh-Token")
    if expected and provided != expected:
        return jsonify({"error": "Unauthorized"}), 401
    stats = run_pipeline()
    return jsonify({"ok": True, "stats": stats})

# (Optionnel) route d'accueil
@app.get("/")
def home():
    return "✅ API 'En Pôle Position' News est en ligne. Endpoints: /news, /refresh (POST), /health"

# -------------------------------
# Boot
# -------------------------------
if __name__ == "__main__":
    init_db()
    # Lancer une première ingestion au démarrage
    try:
        print("[BOOT] Ingestion initiale…")
        stats = run_pipeline()
        print(f"[BOOT] Stats: {stats}")
    except Exception as e:
        print(f"[BOOT][ERROR] {e}")

    # Scheduler toutes les X minutes
    scheduler.add_job(scheduled_job, "interval", minutes=FETCH_INTERVAL_MINUTES, id="news_job", replace_existing=True)
    scheduler.start()

    port = int(os.getenv("PORT", "10000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
