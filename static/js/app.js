async function loadArticles() {
    try {
        let response = await fetch("/api/articles");
        let data = await response.json();

        let container = document.getElementById("articles");
        container.innerHTML = "";

        data.forEach(article => {
            let div = document.createElement("div");
            div.className = "article";
            div.innerHTML = `
                <h2>${article.title}</h2>
                <p>${article.summary}</p>
                <a href="${article.link}" target="_blank">Lire l'article complet</a>
                <p><em>Source : ${article.source}</em></p>
            `;
            container.appendChild(div);
        });
    } catch (err) {
        console.error("Erreur chargement articles:", err);
    }
}

document.addEventListener("DOMContentLoaded", loadArticles);
