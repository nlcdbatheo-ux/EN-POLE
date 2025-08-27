document.addEventListener("DOMContentLoaded", () => {
    console.log("Page loaded — scripts working!");

    // Exemple : ajouter un effet simple aux articles
    const articles = document.querySelectorAll(".article");
    articles.forEach(article => {
        article.addEventListener("mouseover", () => {
            article.style.boxShadow = "0 0 20px rgba(255, 235, 59, 0.8)";
        });
        article.addEventListener("mouseout", () => {
            article.style.boxShadow = "0 0 15px rgba(255, 0, 0, 0.5)";
        });
    });
});
