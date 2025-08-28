document.addEventListener("DOMContentLoaded", () => {
    console.log("🚀 En Pole chargé avec succès !");

    // Animation légère sur les cartes
    const cards = document.querySelectorAll(".card");
    cards.forEach(card => {
        card.addEventListener("mouseover", () => {
            card.style.boxShadow = "0 6px 20px rgba(225,6,0,0.5)";
        });
        card.addEventListener("mouseout", () => {
            card.style.boxShadow = "0 4px 15px rgba(0,0,0,0.6)";
        });
    });
});
