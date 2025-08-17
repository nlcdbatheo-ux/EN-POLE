const newsContainer = document.getElementById("news");

// Fonction pour afficher les news
function displayNews(items) {
    newsContainer.innerHTML = ""; // reset
    items.forEach(item => {
        const el = document.createElement("div");
        el.classList.add("news-item");
        el.innerHTML = `
            <h3>${item.title}</h3>
            <p>${item.summary}</p>
            <a href="${item.url}" target="_blank">Lire l'article</a>
            <small>Publié le ${new Date(item.published_at).toLocaleString()} — Sources: ${item.sources.join(", ")}</small>
        `;
        newsContainer.appendChild(el);
    });
}

// Fonction pour charger les news depuis le backend
async function loadNews() {
    try {
        const response = await fetch("https://en-pole.onrender.com/news?limit=20");
        if (!response.ok) throw new Error(`Erreur HTTP ${response.status}`);
        const data = await response.json();
        displayNews(data.items);
    } catch (err) {
        newsContainer.innerHTML = `<p style="color:red;">Erreur chargement actus : ${err.message}</p>`;
    }
}

// Charger au démarrage
loadNews();

// Rafraîchir toutes les 2 minutes
setInterval(loadNews, 120000);
