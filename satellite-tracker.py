#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from datetime import datetime, timezone
import requests
import math
from PIL import Image, ImageTk

try:
    from skyfield.api import load, EarthSatellite
except ImportError:
    exit(1)

MAP_IMAGE_PATH = "world_map.png"
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 580

FALLBACK_L1 = "1 25544U 98067A   26174.52153935  .00014324  00000-0  25432-3 0  9997"
FALLBACK_L2 = "2 25544  51.6394 120.3412 0005317 291.5023 162.3412 15.49503127573843"

class SpaceEngine:
    def __init__(self):
        self.ts = load.timescale()
        self.satellite = None
        self.using_fallback = False
        self.refresh_tle()

    def refresh_tle(self):
        url = "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS%20(ZARYA)&FORMAT=TLE"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                if len(lines) >= 3:
                    self.satellite = EarthSatellite(lines[1].strip(), lines[2].strip(), 'ISS', self.ts)
                    self.using_fallback = False
                    return
        except Exception:
            pass
        
        self.satellite = EarthSatellite(FALLBACK_L1, FALLBACK_L2, 'ISS', self.ts)
        self.using_fallback = True

    def get_position_at(self, dt: datetime):
        t = self.ts.from_datetime(dt)
        geocentric = self.satellite.at(t)
        subpoint = geocentric.subpoint()
        
        lat = subpoint.latitude.degrees
        lon = subpoint.longitude.degrees
        alt_km = subpoint.elevation.km
        
        velocity_vector = geocentric.velocity.km_per_s
        speed_kms = math.sqrt(sum(v**2 for v in velocity_vector))
        speed_kmh = speed_kms * 3600.0
        
        return lat, lon, alt_km, speed_kmh

    def compute_trajectory(self, points_count=120, step_minutes=1):
        path = []
        start_time = datetime.now(timezone.utc)
        
        for i in range(points_count):
            delta_seconds = i * step_minutes * 60
            future_dt = datetime.fromtimestamp(start_time.timestamp() + delta_seconds, timezone.utc)
            lat, lon, _, _ = self.get_position_at(future_dt)
            path.append((lat, lon))
            
        return path


class TrackerApplication:
    def __init__(self, root, engine: SpaceEngine):
        self.root = root
        self.root.title("Live Orbital Satellite Tracker - ISS")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(False, False)
        
        self.engine = engine
        self.blink_state = True
        
        self.build_ui()
        self.refresh_loop()

    def build_ui(self):
        self.canvas = tk.Canvas(self.root, width=WINDOW_WIDTH, height=512, bg="#03071E", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        try:
            self.raw_img = Image.open(MAP_IMAGE_PATH).resize((WINDOW_WIDTH, 512))
            self.map_bg = ImageTk.PhotoImage(self.raw_img)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.map_bg)
        except FileNotFoundError:
            self.canvas.configure(bg="#0B132B")

        self.status_bar = tk.Frame(self.root, bg="#1C2541", height=68)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.lbl_status = tk.Label(self.status_bar, text="SIGNAL: ...", fg="orange", bg="#1C2541", font=("Courier", 11, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=20)
        
        self.lbl_coords = tk.Label(self.status_bar, text="LAT: --.----° | LON: --.----°", fg="#6FFFE6", bg="#1C2541", font=("Courier", 11, "bold"))
        self.lbl_coords.pack(side=tk.LEFT, expand=True)
        
        self.lbl_telemetry = tk.Label(self.status_bar, text="ALT: --- km | V: --- km/h", fg="#6FFFE6", bg="#1C2541", font=("Courier", 11, "bold"))
        self.lbl_telemetry.pack(side=tk.RIGHT, padx=20)

    def geo_to_canvas_pixels(self, lat: float, lon: float):
        x = ((lon + 180.0) / 360.0) * WINDOW_WIDTH
        y = ((90.0 - lat) / 180.0) * 512
        return int(x), int(y)

    def draw_radio_footprint(self, cx: int, cy: int, alt_km: float):
        R_EARTH = 6378.137
        if alt_km <= 0: return
        
        alpha = math.acos(R_EARTH / (R_EARTH + alt_km))
        pixel_radius = (alpha / (2 * math.pi)) * WINDOW_WIDTH
        
        self.canvas.create_oval(
            cx - pixel_radius, cy - pixel_radius, 
            cx + pixel_radius, cy + pixel_radius, 
            outline="#6FFFE6", width=1, dash=(4, 4), tags="render"
        )

    def refresh_loop(self):
        self.canvas.delete("render")
        current_utc = datetime.now(timezone.utc)
        time_str = current_utc.strftime("%H:%M:%S UTC")
        
        try:
            lat, lon, alt, speed = self.engine.get_position_at(current_utc)
            self.blink_state = not self.blink_state
            source_info = " (LOCAL)" if self.engine.using_fallback else " (CELESTRAK)"
            
            self.lbl_status.config(text=f"[{time_str}] SIGNAL: OK{source_info}", fg="#52B788")
            self.lbl_coords.config(text=f"LAT: {lat:+.4f}° | LON: {lon:+.4f}°")
            self.lbl_telemetry.config(text=f"ALT: {alt:.2f} km | VITESSE: {int(speed)} km/h")
            
            orbit_points = self.engine.compute_trajectory()
            for i in range(len(orbit_points) - 1):
                lat1, lon1 = orbit_points[i]
                lat2, lon2 = orbit_points[i+1]
                
                if abs(lon1 - lon2) < 250:
                    x1, y1 = self.geo_to_canvas_pixels(lat1, lon1)
                    x2, y2 = self.geo_to_canvas_pixels(lat2, lon2)
                    self.canvas.create_line(x1, y1, x2, y2, fill="#FFB703", width=2, dash=(3, 3), tags="render")
            
            sat_x, sat_y = self.geo_to_canvas_pixels(lat, lon)
            self.draw_radio_footprint(sat_x, sat_y, alt)
            
            sat_color = "#E63946" if self.blink_state else "#FFFFFF"
            self.canvas.create_oval(sat_x - 6, sat_y - 6, sat_x + 6, sat_y + 6, fill=sat_color, outline="white", width=1, tags="render")
            self.canvas.create_text(sat_x, sat_y - 16, text="ISS", fill="white", font=("Arial", 9, "bold"), tags="render")
            
        except Exception as e:
            self.lbl_status.config(text=f"[{time_str}] ERROR ENGINE", fg="#E63946")
            print(e)

        self.root.after(1000, self.refresh_loop)


if __name__ == "__main__":
    space_tracker_engine = SpaceEngine()
    main_window = tk.Tk()
    app = TrackerApplication(main_window, space_tracker_engine)
    main_window.mainloop()