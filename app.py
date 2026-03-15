from flask import Flask, request, jsonify, render_template
import urllib.request
import urllib.parse
import json
import anthropic
import os

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
TICKETMASTER_KEY = os.environ.get("TICKETMASTER_API_KEY")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ville-depuis-coords", methods=["POST"])
def ville_depuis_coords():
    lat = request.json["lat"]
    lon = request.json["lon"]

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=50,
        messages=[{"role": "user", "content": f"Quelle est la ville la plus proche des coordonnées GPS latitude={lat}, longitude={lon} ? Réponds uniquement avec le nom de la ville, rien d'autre."}]
    )
    ville = message.content[0].text.strip()
    return jsonify({"ville": ville})

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

    # Claude choisit l'icône, formule la réponse et donne un conseil chauffeur
    message2 = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": f"""Météo à {ville} : {meteo_now['temperature']}°C, vent {meteo_now['windspeed']} km/h, code météo {meteo_now['weathercode']}.
Tu parles à un chauffeur VTC.
Réponds uniquement en JSON avec ce format exactement :
{{"icone": "☀️", "reponse": "Une phrase sur la météo en français", "activite": "Un conseil utile pour le chauffeur VTC en lien avec la météo"}}
Choisis l'icône parmi : ☀️ (beau temps), ⛅ (nuageux), 🌧️ (pluie), ⛈️ (orage), ❄️ (neige), 🌫️ (brouillard)"""}]
    )

    texte = message2.content[0].text.strip()
    texte = texte.replace("```json", "").replace("```", "").strip()
    resultat = json.loads(texte)
    resultat["previsions"] = previsions

    # Appel API Ticketmaster pour les événements
    ville_encodee = urllib.parse.quote(ville)
    tm_url = f"https://app.ticketmaster.com/discovery/v2/events.json?city={ville_encodee}&size=3&apikey={TICKETMASTER_KEY}"
    try:
        with urllib.request.urlopen(tm_url) as response:
            tm_data = json.loads(response.read())
        evenements = []
        if "_embedded" in tm_data:
            for event in tm_data["_embedded"]["events"]:
                evenements.append({
                    "nom": event["name"],
                    "date": event["dates"]["start"].get("localDate", "Date inconnue"),
                    "lieu": event["_embedded"]["venues"][0]["name"] if "_embedded" in event else "Lieu inconnu"
                })
        resultat["evenements"] = evenements
    except:
        resultat["evenements"] = []

    return jsonify(resultat)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)