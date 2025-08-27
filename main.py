# main.py
# En Pôle Position – API News F1
# (c) 2025 – Prêt pour Render / déploiement container
import os
import json
import sqlite3
import re
import time
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from dateutil import parser as dateparser

# ---------- OpenAI 1.x ----------
from openai import OpenAI
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)

# ---------- Logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("en-pole")

# ---------- Config ----------
DEFAULT_SOURCES: List[Tuple[str, str]] = [
    ("Motorsport.com", "https://www.motorsport.com/rss/f1/news/"),
    ("Autosport",      "https://www.autosport.com/rss/f1"),
    ("RaceFans",       "https://www.racefans.net/feed/"),
    ("PlanetF1",       "https://www.planetf1.com/feed/"),
    ("Nextgen-Auto",   "https://motorsport.nextgen-auto.com/spip.php?page=backend"),
]
SOURCES: List[Tuple[str, str]] = []
for i, (name, url) in enumerate(DEFAULT_SOURCES, start=1):
    env_url = os.getenv(f"NEWS_SOURCE_{i}_URL", "").strip()
    SOURCES.append((name, env_url if env_url else url))

FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "10"))
CONFIRMATION_MIN_SOURCES = int(os.getenv("CONFIRMATION_MIN_SOURCES", "2"))
MAX_ITEMS_PER_SOURCE = int(os.getenv("MAX_ITEMS_PER_SOURCE", "30"))
OPENAI_TIMEOUT_S = int(os.getenv("OPENAI_TIMEOUT_S", "15"))
MAX_OPENAI_CALLS_PER_RUN = int(os.getenv("MAX_OPENAI_CALLS_PER_RUN", "40"))
DB_PATH = os.getenv("DB_PATH", "news.db")
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "*")  # ex: "https://nlcdbatheo-ux.github.io,https://ton-domaine"

# ---------- Flask ----------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [o.strip() for o in FRONTEND_ORIGINS.split(",")] if FRONTEND_ORIGINS != "*" else "*"}})

# ---------- DB ----------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE,
            title TEXT,
            summary TEXT,
            url TEXT,
            sources_json TEXT,
            published_at TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            description TEXT,
            url TEXT,
            published_at TEXT,
            fetched_at TEXT
        )
    """)
    conn.commit()
    conn.close()

# ---------- Utils ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def to_iso(dt) -> str:
    if isinstance(dt, str) and dt:
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
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", "", text)
    # accents et caractères F1 fréquents conservés
    text = re.sub(r"[^a-z0-9áàâäãåçéèêëíìîïñóòôöõúùûüýÿ'’ -]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

STOPWORDS = set("""
f1 formule formula one grand prix gp le la les de du des d' l' un une au aux en et à a the for of in on
""".split())

def key_from_title(title: str) -> str:
    norm = normalize_text(title)
    tokens = [t for t in norm.split() if t not in STOPWORDS and len(t) > 2]
    tokens = sorted(tokens)[:8]
    key = "-".join(tokens)
    return str(abs(hash(key)))

def jaccard(a: str, b: str) -> float:
    sa = set([t for t in normalize_text(a).split() if t not in STOPWORDS])
    sb = set([t for t in normalize_text(b).split() if t not in STOPWORDS])
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / max(1, union)

@dataclass
class Item:
    source: str
    title: str
    description: str
    url: str
    published_at: str
    fetched_at: str

# ---------- Fetch RSS ----------
def fetch_source(name: str, url: str) -> List[Dict[str, Any]]:
    feed = feedparser.parse(url)
    out: List[Dict[str, Any]] = []
    fetched_at = now_iso()
    for e in feed.entries[:MAX_ITEMS_PER_SOURCE]:
        title = (e.get("title") or "").strip()
        if not title:
            continue
        summary = e.get("summary", "") or e.get("description", "")
        link = e.get("link", "") or ""
        raw_pub = e.get("published") or e.get("updated") or ""
        try:
            if hasattr(e, "published_parsed") and e.published_parsed:
                published_dt = datetime.fromtimestamp(time.mktime(e.published_parsed), tz=timezone.utc)
            elif hasattr(e, "updated_parsed") and e.updated_parsed:
                published_dt = datetime.fromtimestamp(time.mktime(e.updated_parsed), tz=timezone.utc)
            else:
                published_dt = dateparser.parse(raw_pub) if raw_pub else datetime.now(timezone.utc)
            published_iso = to_iso(published_dt)
        except Exception:
            published_iso = now_iso()
        out.append({
            "source": name,
            "title": title,
            "description": summary,
            "url": link,
            "published_at": published_iso,
            "fetched_at": fetched_at,
        })
    log.info(f"[FETCH] {name}: {len(out)} items")
    return out

def fetch_all_sources() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for name, url in SOURCES:
        try:
            items.extend(fetch_source(name, url))
        except Exception as e:
            log.warning(f"[WARN] Échec source {name}: {e}")
    return items

# ---------- Grouping ----------
def merge_groups(items: List[Dict[str, Any]], threshold_title: float = 0.55) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    for it in items:
        placed = False
        for g in groups:
            # Comparer sur le titre en priorité
            if jaccard(g['title'], it['title']) >= threshold_title:
                g['items'].append(it)
                # Garder le titre « plus informatif »
                if len(it['title']) > len(g['title']):
                    g['title'] = it['title']
                placed = True
                break
        if not placed:
            groups.append({"title": it['title'], "items": [it]})
    # Construire stories
    stories: List[Dict[str, Any]] = []
    for g in groups:
        srcs = sorted(list({i['source'] for i in g['items']}))
        urls = [i['url'] for i in g['items'] if i.get('url')]
        dates = [i['published_at'] for i in g['items'] if i.get('published_at')]
        pub = min(dates) if dates else now_iso()
        raw_text = "\n\n".join([f"[{i['source']}] {i['title']}\n{i.get('description','')}" for i in g['items']])
        stories.append({
            "title": g["title"],
            "sources": srcs,
            "urls": urls,
            "published_at": pub,
            "raw_text": raw_text,
            "items": g["items"],
        })
    return stories

# ---------- OpenAI helpers ----------
SYSTEM_REWRITE = (
    "Tu es un journaliste spécialisé en Formule 1 pour le site « En Pôle Position ».\n"
    "Rédige en français, clair, concis et factuel. Ne publie que ce qui est confirmé par plusieurs sources.\n"
    "Ajoute, si utile, un contexte minimal (équipe, pilotes, calendrier), aère en 3–5 phrases, évite toute spéculation."
)

def openai_call_with_retry(messages: List[Dict[str, str]], max_tokens: int, temperature: float = 0.2, n_retry: int = 2) -> Optional[str]:
    if client is None:
        return None
    last_err = None
    for attempt in range(n_retry + 1):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=OPENAI_TIMEOUT_S,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            log.warning(f"[OpenAI][attempt {attempt+1}] {e}")
            time.sleep(1.5 * (attempt + 1))
    log.error(f"[OpenAI] Échec après retries: {last_err}")
    return None

def are_texts_same_story(t1: str, t2: str) -> Optional[bool]:
    """
    Demande à OpenAI si deux textes parlent du même sujet (oui/non).
    Retourne True/False/None (si indisponible).
    """
    messages = [
        {"role": "system", "content": "Réponds uniquement par 'oui' ou 'non'."},
        {"role": "user", "content": f"Ces deux brèves F1 parlent-elles du même sujet (même information, même annonce) ?\n\nTexte A:\n{t1}\n\nTexte B:\n{t2}\n\nRéponds par 'oui' ou 'non' uniquement."}
    ]
    ans = openai_call_with_retry(messages, max_tokens=3, temperature=0)
    if ans is None:
        return None
    ans = ans.lower()
    if "oui" in ans:
        return True
    if "non" in ans:
        return False
    return None

def reformulate_story(title: str, raw_text: str, urls: List[str]) -> str:
    user = (
        f"Titre provisoire: {title}\n\n"
        f"Sources multiples (extraits):\n{raw_text}\n\n"
        f"Liens (jusqu'à 5):\n" + "\n".join(urls[:5]) + "\n\n"
        "Tâche: rédige une brève de 3–5 phrases, uniquement sur les éléments factuels communs aux sources. "
        "Inclue une phrase sur l'état de confirmation (ex: 'confirmé par X sources'). "
        "Évite le sensationnalisme et les redondances. Ne mentionne pas l'usage d'IA."
    )
    messages = [
        {"role": "system", "content": SYSTEM_REWRITE},
        {"role": "user", "content": user},
    ]
    out = openai_call_with_retry(messages, max_tokens=280, temperature=0.3)
    return out or title

# ---------- Persistence ----------
def save_raw_items(raw_items: List[Dict[str, Any]]) -> None:
    if not raw_items:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.executemany("""
        INSERT INTO news_raw (source, title, description, url, published_at, fetched_at)
        VALUES (:source, :title, :description, :url, :published_at, :fetched_at)
    """, raw_items)
    conn.commit()
    conn.close()

def already_published(key_hash: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM news WHERE key_hash = ? LIMIT 1", (key_hash,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def publish_story(title: str, summary: str, url: str, sources: List[str], published_at: str) -> bool:
    key_hash = key_from_title(title)
    if already_published(key_hash):
        return False
    conn = get_db()
    cur = conn.cursor()
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
    log.info(f"[PUBLISHED] {title} | sources={', '.join(sources)}")
    return True

# ---------- Pipeline ----------
def validate_group_semantically(items: List[Dict[str, Any]], max_pairs: int = 6) -> bool:
    """
    Optionnel: validation sémantique par OpenAI sur quelques paires (titre+desc).
    On s'arrête si on voit 2 confirmations "oui".
    """
    if client is None:
        # sans OpenAI, on accepte si multi-sources suffisant
        return True
    pairs_checked = 0
    confirmations = 0
    texts = []
    for it in items:
        t = (it["title"] + "\n" + (it.get("description") or "")).strip()
        texts.append(t)
    # comparer un petit sous-ensemble (cartésien limité)
    for i in range(len(texts)):
        for j in range(i+1, len(texts)):
            if pairs_checked >= max_pairs:
                break
            res = are_texts_same_story(texts[i], texts[j])
            pairs_checked += 1
            if res is True:
                confirmations += 1
            if confirmations >= 2:
                return True
        if pairs_checked >= max_pairs:
            break
    # Si aucune confirmation positive par l'IA, on reste prudent
    return confirmations > 0

def run_pipeline() -> Dict[str, Any]:
    """
    1) Fetch 5 flux RSS
    2) Sauvegarde brut (news_raw)
    3) Grouping par similarité
    4) Filtre groupes >= N sources
    5) Validation sémantique OpenAI (optionnelle)
    6) Reformulation OpenAI
    7) Publication SQLite
    """
    log.info("[PIPELINE] Démarrage…")
    raw = fetch_all_sources()
    log.info(f"[PIPELINE] {len(raw)} articles bruts")
    if not raw:
        return {"fetched": 0, "groups": 0, "published": 0}

    save_raw_items(raw)

    groups = merge_groups(raw, threshold_title=0.55)
    log.info(f"[PIPELINE] {len(groups)} groupes candidats")

    openai_calls = 0
    published_count = 0

    for g in groups:
        if len(g["sources"]) < CONFIRMATION_MIN_SOURCES:
            continue

        # Validation sémantique (si OpenAI dispo) sous quota
        sem_ok = True
        if client is not None and openai_calls < MAX_OPENAI_CALLS_PER_RUN:
            sem_ok = validate_group_semantically(g["items"])
            openai_calls += 1  # on compte cette validation comme 1 « coût virtuel »
        if not sem_ok:
            continue

        # Reformulation (compte aussi dans le budget d'appels)
        summary = g["title"]
        if client is not None and openai_calls < MAX_OPENAI_CALLS_PER_RUN:
            summary = reformulate_story(g["title"], g["raw_text"], g["urls"])
            openai_calls += 1

        main_url = g["urls"][0] if g["urls"] else ""
        if publish_story(title=g["title"], summary=summary, url=main_url, sources=g["sources"], published_at=g["published_at"]):
            published_count += 1

    stats = {"fetched": len(raw), "groups": len(groups), "published": published_count}
    log.info(f"[PIPELINE] Stats: {stats}")
    return stats

# ---------- Scheduler ----------
scheduler = BackgroundScheduler(daemon=True)

def scheduled_job():
    try:
        stats = run_pipeline()
        log.info(f"[SCHEDULED] Stats: {stats}")
        # message info si rien de publié à l'heure pile
        if stats.get("published", 0) == 0:
            now = datetime.now(timezone.utc)
            if now.minute == 0:
                publish_story(
                    title="⏳ Pas de nouvelles informations",
                    summary="Pas de nouvelles informations confirmées pour l’instant. Revenez plus tard.",
                    url="",
                    sources=["System"],
                    published_at=now_iso(),
                )
                log.info("[INFO] Message 'pas de nouvelles' ajouté.")
    except Exception as e:
        log.exception(f"[SCHEDULED][ERROR] {e}")

# ---------- API ----------
@app.get("/health")
def health():
    return jsonify({"status": "ok", "time": now_iso(), "openai": bool(client)})

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
    expected = os.getenv("REFRESH_TOKEN", "").strip()
    provided = request.headers.get("X-Refresh-Token", "")
    if expected and provided != expected:
        return jsonify({"error": "Unauthorized"}), 401
    stats = run_pipeline()
    return jsonify({"ok": True, "stats": stats})

@app.get("/")
def home():
    return "✅ API En Pôle Position – endpoints: /news, /refresh (POST), /health"

# ---------- Boot ----------
def boot():
    init_db()
    log.info("[BOOT] Ingestion initiale…")
    try:
        stats = run_pipeline()
        log.info(f"[BOOT] Stats: {stats}")
    except Exception as e:
        log.exception(f"[BOOT][ERROR] {e}")

    # Démarrer le scheduler après le premier run
    scheduler.add_job(scheduled_job, "interval", minutes=FETCH_INTERVAL_MINUTES, id="news_job", replace_existing=True)
    scheduler.start()

if __name__ == "__main__":
    boot()
    port = int(os.getenv("PORT", "10000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    # Très important pour Render : host=0.0.0.0 et port=PORT
    app.run(host="0.0.0.0", port=port, debug=debug)
