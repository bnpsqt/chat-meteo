from flask import Flask, request, jsonify, render_template
import urllib.request
import json
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
client = anthropic.Anthropic(api_key="ANTHROPIC_API_KEY")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/meteo", methods=["POST"])
def meteo():
    ville = request.json["ville"]

    # Claude trouve les coordonnées
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=100,
        messages=[{"role": "user", "content": f"Coordonnées GPS de {ville}. Réponds uniquement latitude,longitude. Exemple: 48.85,2.35"}]
    )
    lat, lon = message.content[0].text.strip().split(",")

    # Appel API météo avec prévisions 7 jours
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())

    meteo_now = data["current_weather"]
    daily = data["daily"]

    # Prévisions 7 jours
    previsions = []
    for i in range(7):
        previsions.append({
            "date": daily["time"][i],
            "max": daily["temperature_2m_max"][i],
            "min": daily["temperature_2m_min"][i],
            "code": daily["weathercode"][i]
        })

    # Claude choisit l'icône, formule la réponse et suggère une activité
    message2 = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": f"""Météo à {ville} : {meteo_now['temperature']}°C, vent {meteo_now['windspeed']} km/h, code météo {meteo_now['weathercode']}.
Réponds uniquement en JSON avec ce format exactement :
{{"icone": "☀️", "reponse": "Une phrase sympa en français", "activite": "Une suggestion d'activité en famille adaptée à cette météo, en une phrase"}}
Choisis l'icône parmi : ☀️ (beau temps), ⛅ (nuageux), 🌧️ (pluie), ⛈️ (orage), ❄️ (neige), 🌫️ (brouillard)"""}]
    )

    texte = message2.content[0].text.strip()
    texte = texte.replace("```json", "").replace("```", "").strip()
    resultat = json.loads(texte)
    resultat["previsions"] = previsions
    return jsonify(resultat)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)