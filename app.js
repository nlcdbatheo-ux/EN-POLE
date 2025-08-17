// Sélection des éléments du DOM
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");

// Fonction pour afficher un message dans le chat
function addMessage(sender, message) {
    const messageElement = document.createElement("div");
    messageElement.classList.add("message", sender);
    messageElement.textContent = message;
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

const BOT_URL = "https://en-pole.onrender.com/chat";  // <- ajoute /chat

chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userMessage = chatInput.value.trim();
    if (!userMessage) return;

    addMessage("user", userMessage);
    chatInput.value = "";
    chatInput.disabled = true;

    try {
        // Envoie la requête au bot Render
        const response = await fetch(BOT_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: userMessage }) // <- "message", pas "prompt"
        });

        if (!response.ok) {
            throw new Error(`Erreur HTTP ${response.status}`);
        }

        const data = await response.json();
        const botMessage = data.reply || "Le bot n'a pas répondu."; // <- "reply", pas "response"

        addMessage("bot", botMessage);

    } catch (error) {
        addMessage("bot", `Erreur : impossible de contacter le bot.\n${error.message}`);
    } finally {
        chatInput.disabled = false;
        chatInput.focus();
    }
});
