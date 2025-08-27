async function fetchNews() {
    try {
        const res = await fetch('/news');
        const data = await res.json();
        const container = document.getElementById('news-container');
        container.innerHTML = '';
        data.forEach(article => {
            const div = document.createElement('div');
            div.classList.add('article');
            div.innerHTML = `
                <a href="${article.link}" target="_blank">${article.title}</a>
                <p>${article.published}</p>
            `;
            container.appendChild(div);
        });
    } catch (err) {
        console.error('Erreur:', err);
    }
}

// Actualiser toutes les 5 minutes côté client
setInterval(fetchNews, 5 * 60 * 1000);
fetchNews();
