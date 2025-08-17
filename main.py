from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from openai import OpenAI

app = Flask(__name__)
CORS(app)  # Autorise les appels cross-origin

# Configure OpenAI avec ta clé
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "")

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # modèle rapide et pas cher
            messages=[
                {"role": "system", "content": "Tu es le bot 'En Pôle Position', expert en Formule 1."},
                {"role": "user", "content": user_message}
            ]
        )

        bot_reply = response.choices[0].message.content
        return jsonify({"reply": bot_reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
