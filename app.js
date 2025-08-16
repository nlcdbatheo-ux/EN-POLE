// Sélection des éléments du DOM
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");

// URL de ton bot Render
const BOT_URL = "https://en-pole-bot.onrender.com/";

// Fonction pour afficher un message dans le chat
function addMessage(sender, message) {
    const messageElement = document.createElement("div");
    messageElement.classList.add("message", sender);
    messageElement.textContent = message;
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Événement lors de l'envoi du formulaire
chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userMessage = chatInput.value.trim();
    if (!userMessage) return;

    // Affiche le message de l'utilisateur
    addMessage("user", userMessage);
    chatInput.value = "";
    chatInput.disabled = true;

    try {
        // Envoie la requête au bot Render
        const response = await fetch(BOT_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: userMessage })
        });

        if (!response.ok) {
            throw new Error(`Erreur HTTP ${response.status}`);
        }

        const data = await response.json();
        const botMessage = data.response || "Le bot n'a pas répondu.";

        // Affiche la réponse du bot
        addMessage("bot", botMessage);

    } catch (error) {
        // En cas d'erreur (bot inaccessible, etc.)
        addMessage("bot", `Erreur : impossible de contacter le bot.\n${error.message}`);
    } finally {
        chatInput.disabled = false;
        chatInput.focus();
    }
});
