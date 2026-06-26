#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, jsonify, render_template_string
from datetime import datetime, timezone
import requests
import math

try:
    from skyfield.api import load, EarthSatellite
except ImportError:
    print("Erreur : executez 'pip install flask skyfield requests'")
    exit(1)

app = Flask(__name__)

class SpaceEngine:
    def __init__(self):
        self.ts = load.timescale()
        self.satellite = None
        self.refresh_tle()

    def refresh_tle(self):
        url = "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS%20(ZARYA)&FORMAT=TLE"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                if len(lines) >= 3:
                    self.satellite = EarthSatellite(lines[1].strip(), lines[2].strip(), 'ISS', self.ts)
                    return
        except Exception:
            pass
        
        l1 = "1 25544U 98067A   26174.52153935  .00014324  00000-0  25432-3 0  9997"
        l2 = "2 25544  51.6394 120.3412 0005317 291.5023 162.3412 15.49503127573843"
        self.satellite = EarthSatellite(l1, l2, 'ISS', self.ts)

    def get_data(self):
        now = datetime.now(timezone.utc)
        t = self.ts.from_datetime(now)
        geocentric = self.satellite.at(t)
        subpoint = geocentric.subpoint()
        
        velocity = geocentric.velocity.km_per_s
        speed_kmh = math.sqrt(sum(v**2 for v in velocity)) * 3600.0
        
        return {
            "lat": subpoint.latitude.degrees,
            "lon": subpoint.longitude.degrees,
            "alt": round(subpoint.elevation.km, 2),
            "speed": int(speed_kmh),
            "time": now.strftime("%H:%M:%S UTC")
        }

    def get_orbit_path(self):
        path = []
        now = datetime.now(timezone.utc)
        for i in range(120):
            future_dt = datetime.fromtimestamp(now.timestamp() + (i * 60), timezone.utc)
            t = self.ts.from_datetime(future_dt)
            subp = self.satellite.at(t).subpoint()
            path.append([subp.latitude.degrees, subp.longitude.degrees])
        return path

engine = SpaceEngine()

@app.route('/api/iss')
def api_iss():
    return jsonify(engine.get_data())

@app.route('/api/orbit')
def api_orbit():
    return jsonify(engine.get_orbit_path())

@app.route('/')
def home():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ISS 3D Space Tracker</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://unpkg.com/three"></script>
        <script src="https://unpkg.com/globe.gl"></script>
        <style>
            html, body { height: 100%; margin: 0; padding: 0; background: #000; font-family: monospace; overflow: hidden; }
            #globeViz { width: 100%; height: 100%; position: absolute; top: 0; left: 0; z-index: 1; }
            #telemetry { 
                position: absolute; bottom: 20px; left: 20px; z-index: 10; 
                background: rgba(10, 10, 15, 0.85); color: #6fffe6; 
                padding: 15px 20px; border-radius: 6px; box-shadow: 0 0 20px rgba(0,255,230,0.15);
                font-size: 13px; pointer-events: none; border: 1px solid #1f2937;
            }
            .stat-val { color: #fff; font-weight: bold; }
        </style>
    </head>
    <body>
        <div id="telemetry">
            [<span id="time" class="stat-val">--:--:--</span>] ISS 3D TRACKER<br>
            POS : <span id="coords" class="stat-val">LAT: -- | LON: --</span><br>
            ALT : <span id="alt" class="stat-val">--</span> km | V: <span id="speed" class="stat-val">--</span> km/h
        </div>
        
        <div id="globeViz"></div>

        <script>
            // Initialisation du globe
            const world = Globe()
                (document.getElementById('globeViz'))
                .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg')
                .showAtmosphere(true)
                .atmosphereColor('#2187ab')
                .atmosphereAltitude(0.15);

            world.controls().autoRotate = true;
            world.controls().autoRotateSpeed = 0.2;

            // Variable globale pour stocker l'orbite afin de ne pas la perdre
            let currentOrbitPoints = [];

            function loadOrbit() {
                fetch('/api/orbit')
                    .then(res => res.json())
                    .then(points => {
                        currentOrbitPoints = points;
                        // On applique le tracé
                        world.pathsData([currentOrbitPoints])
                             .pathColor(() => '#ffb703')
                             .pathWidth(2);
                    })
                    .catch(err => console.error("Erreur API Orbite:", err));
            }

            function updateTracker() {
                fetch('/api/iss')
                    .then(res => res.json())
                    .then(data => {
                        const issData = [{
                            lat: data.lat,
                            lng: data.lon,
                            alt: 0.12,
                            img: '/static/iss.png'
                        }];

                        // Rafraîchir l'icône de l'ISS
                        world.htmlElementsData(issData)
                             .htmlElement(d => {
                                 const el = document.createElement('img');
                                 el.src = d.img;
                                 el.style.width = '40px';
                                 el.style.height = '40px';
                                 el.style.pointerEvents = 'none';
                                 return el;
                             });

                        // RENTRÉE DANS L'ORDRE : On force le globe à maintenir le tracé de l'orbite
                        if (currentOrbitPoints.length > 0) {
                            world.pathsData([currentOrbitPoints]);
                        }

                        // Mise à jour de la télémétrie
                        document.getElementById('time').innerText = data.time;
                        document.getElementById('coords').innerText = `LAT: ${data.lat.toFixed(4)}° | LON: ${data.lon.toFixed(4)}°`;
                        document.getElementById('alt').innerText = data.alt;
                        document.getElementById('speed').innerText = data.speed;
                    })
                    .catch(err => console.error("Erreur API ISS:", err));
            }

            // Démarrage propre
            loadOrbit();
            // Petit délai pour laisser l'orbite se charger avant le premier update de l'icône
            setTimeout(updateTracker, 500); 
            
            setInterval(updateTracker, 1000);
            setInterval(loadOrbit, 60000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)