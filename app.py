from flask import Flask, request, jsonify, render_template
import urllib.request
import urllib.parse
import json
import anthropic
import os
from datetime import datetime, timezone

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

    # Météo + prévisions 7 jours
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())

    meteo_now = data["current_weather"]
    daily = data["daily"]

    previsions = []
    for i in range(7):
        previsions.append({
            "date": daily["time"][i],
            "max": daily["temperature_2m_max"][i],
            "min": daily["temperature_2m_min"][i],
            "code": daily["weathercode"][i]
        })

    # Claude formule la réponse
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

    # Événements selon la ville
    evenements = []
    ville_lower = ville.lower().strip()

    if "paris" in ville_lower:
        try:
            aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            oa_url = f"https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/que-faire-a-paris-/records?where=date_start%3E%3D%22{aujourd_hui}%22&order_by=date_start%20ASC&limit=10"
            with urllib.request.urlopen(oa_url) as response:
                oa_data = json.loads(response.read())
            for event in oa_data.get("results", []):
                nom = event.get("title", "Événement")
                lieu = event.get("address_name") or event.get("address_street") or "Paris"
                date = (event.get("date_start") or "")[:10]
                if nom and date:
                    evenements.append({"nom": nom, "date": date, "lieu": lieu})
        except Exception as e:
            print(f"Paris API error: {e}")

    # Ticketmaster en complément
    try:
        ville_encodee = urllib.parse.quote(ville)
        tm_url = f"https://app.ticketmaster.com/discovery/v2/events.json?city={ville_encodee}&size=5&apikey={TICKETMASTER_KEY}"
        with urllib.request.urlopen(tm_url) as response:
            tm_data = json.loads(response.read())
        if "_embedded" in tm_data:
            for event in tm_data["_embedded"]["events"]:
                evenements.append({
                    "nom": event["name"],
                    "date": event["dates"]["start"].get("localDate", ""),
                    "lieu": event["_embedded"]["venues"][0]["name"] if "_embedded" in event else "Lieu inconnu"
                })
    except Exception as e:
        print(f"Ticketmaster error: {e}")

    # Claude sélectionne les meilleurs événements
    if evenements:
        try:
            message3 = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=500,
                messages=[{"role": "user", "content": f"""Voici une liste d'événements à {ville} : {json.dumps(evenements[:15], ensure_ascii=False)}
Sélectionne les 5 plus importants pour un chauffeur VTC (grands concerts, matchs, festivals, spectacles majeurs).
Réponds uniquement en JSON : [{{"nom": "...", "date": "...", "lieu": "..."}}]"""}]
            )
            texte3 = message3.content[0].text.strip()
            texte3 = texte3.replace("```json", "").replace("```", "").strip()
            resultat["evenements"] = json.loads(texte3)
        except:
            resultat["evenements"] = evenements[:5]
    else:
        resultat["evenements"] = []

    # Prix carburant
    try:
        ville_capitalisee = ville.strip().title()
        params = urllib.parse.urlencode({
            "limit": "10",
            "where": f'ville="{ville_capitalisee}"',
            "order_by": "gazole_prix ASC"
        })
        carb_url = f"https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records?{params}"
        with urllib.request.urlopen(carb_url) as response:
            carb_data = json.loads(response.read())

        carburants = {}
        for station in carb_data.get("results", []):
            adresse = station.get("adresse", "")
            for carb, champ in [("Gazole", "gazole_prix"), ("SP95", "sp95_prix"), ("SP98", "sp98_prix"), ("E10", "e10_prix"), ("E85", "e85_prix")]:
                prix = station.get(champ)
                if prix:
                    if carb not in carburants or prix < carburants[carb]["prix"]:
                        carburants[carb] = {"prix": prix, "adresse": adresse}

        resultat["carburants"] = [
            {"nom": k, "prix": v["prix"], "adresse": v["adresse"]}
            for k, v in sorted(carburants.items())
        ]
    except Exception as e:
        print(f"Carburant error: {e}")
        resultat["carburants"] = []

    # Zones chaudes — Claude analyse tout et prédit
    try:
        heure_actuelle = datetime.now().strftime("%Hh%M")
        jour_semaine = datetime.now().strftime("%A")
        message4 = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=600,
            messages=[{"role": "user", "content": f"""Tu es un expert en mobilité urbaine VTC à {ville}.
Il est {heure_actuelle}, nous sommes {jour_semaine}.
Météo : {meteo_now['temperature']}°C, code {meteo_now['weathercode']}.
Événements aujourd'hui et demain : {json.dumps(resultat['evenements'], ensure_ascii=False)}

Analyse ces données et identifie 3 zones de forte demande VTC pour aujourd'hui/ce soir.
Pour chaque zone, indique le quartier, la raison et le créneau horaire optimal.
Réponds uniquement en JSON :
[{{"zone": "Nom du quartier", "raison": "Explication courte", "creneau": "Ex: 22h-23h30", "intensite": "élevée/moyenne"}}]"""}]
        )
        texte4 = message4.content[0].text.strip()
        texte4 = texte4.replace("```json", "").replace("```", "").strip()
        resultat["zones_chaudes"] = json.loads(texte4)
    except Exception as e:
        print(f"Zones chaudes error: {e}")
        resultat["zones_chaudes"] = []

    return jsonify(resultat)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)