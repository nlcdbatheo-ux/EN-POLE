document.addEventListener("DOMContentLoaded", () => {
  // Récupère #news, ou le crée si absent (sécurise le rendu)
  let newsContainer = document.getElementById("news");
  if (!newsContainer) {
    newsContainer = document.createElement("div");
    newsContainer.id = "news";
    document.body.appendChild(newsContainer);
    console.warn("⚠️ #news était absent dans le HTML, il a été créé automatiquement.");
  }

  const API_URL = "https://en-pole.onrender.com/news?limit=20";

  function showLoading() {
    newsContainer.innerHTML = `<p id="loading">Chargement des actus…</p>`;
  }

  function displayNews(items) {
    newsContainer.innerHTML = ""; // reset
    if (!items || items.length === 0) {
      newsContainer.innerHTML =
        `<div class="news-item"><p>Pas de nouvelles informations cette heure-ci, revenez plus tard.</p></div>`;
      return;
    }
    items.forEach(item => {
      const el = document.createElement("div");
      el.classList.add("news-item");
      el.innerHTML = `
        <h3>${item.title}</h3>
        <p>${item.summary}</p>
        <a href="${item.url}" target="_blank" rel="noopener">Lire l'article</a>
        <small>Publié le ${new Date(item.published_at).toLocaleString()} — Sources: ${item.sources.join(", ")}</small>
      `;
      newsContainer.appendChild(el);
    });
  }

  // fetch avec timeout pour éviter les chargements éternels
  async function fetchWithTimeout(resource, options = {}) {
    const { timeout = 15000, ...rest } = options;
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
      return await fetch(resource, { ...rest, signal: controller.signal, cache: "no-store" });
    } finally {
      clearTimeout(id);
    }
  }

  async function loadNews() {
    showLoading();
    try {
      const response = await fetchWithTimeout(API_URL, { timeout: 15000 });
      if (!response.ok) throw new Error(`Erreur HTTP ${response.status}`);
      const data = await response.json();
      displayNews(data.items);
    } catch (err) {
      console.error(err);
      // même si #news était manquant au départ, on l'a créé, donc ceci s'affichera
      newsContainer.innerHTML = `<p style="color:red;">Erreur chargement actus : ${err.message}</p>`;
    }
  }

  loadNews();
  // Rafraîchir toutes les 2 minutes
  setInterval(loadNews, 120000);
});
