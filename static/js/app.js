async function fetchArticles() {
  const listEl = document.getElementById("articles");
  const emptyEl = document.getElementById("emptyState");
  listEl.innerHTML = skeleton(6);

  try {
    const res = await fetch("/api/articles", { cache: "no-store" });
    const data = await res.json();

    if (!Array.isArray(data) || data.length === 0) {
      listEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      return;
    }

    emptyEl.classList.add("hidden");
    // déjà trié côté serveur, mais on s’assure
    data.sort((a, b) => (a.published > b.published ? -1 : 1));

    const html = data.map(renderCard).join("");
    listEl.innerHTML = html;
  } catch (e) {
    console.error(e);
    listEl.innerHTML = `<div class="error">Erreur de chargement. Réessaie.</div>`;
  }
}

function renderCard(a) {
  const date = formatDate(a.published);
  const text = a.ai_summary && a.ai_summary.trim().length > 0
    ? a.ai_summary
    : (a.summary_raw || "");

  const img = a.image
    ? `<img class="thumb" src="${a.image}" alt="" loading="lazy">`
    : `<div class="thumb thumb--placeholder"></div>`;

  const source = a.credit || a.source || "";

  return `
  <article class="card">
    <a href="${a.link}" class="card__media" target="_blank" rel="noopener noreferrer">
      ${img}
    </a>
    <div class="card__body">
      <h3 class="card__title">
        <a href="${a.link}" target="_blank" rel="noopener noreferrer">${escapeHtml(a.title)}</a>
      </h3>
      <p class="card__text">${escapeHtml(text)}</p>
      <div class="card__meta">
        <span class="chip">${escapeHtml(source)}</span>
        <time>${date}</time>
      </div>
    </div>
  </article>`;
}

function skeleton(n) {
  return Array.from({ length: n }).map(() => `
    <div class="card skeleton">
      <div class="card__media"></div>
      <div class="card__body">
        <div class="line w60"></div>
        <div class="line"></div>
        <div class="line w80"></div>
        <div class="meta"></div>
      </div>
    </div>
  `).join("");
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("fr-FR", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return "";
  }
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

document.addEventListener("DOMContentLoaded", () => {
  fetchArticles();
  document.getElementById("refreshBtn").addEventListener("click", fetchArticles);
});
