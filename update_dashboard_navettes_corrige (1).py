#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NOVACTU SBH — dashboard auto-update
- Fetches trusted public data for Saint-Barthélemy
- Writes data/latest.json for traceability
- Patches index.html so Netlify can serve a static signage-ready page
"""
from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TARGET_FILE = ROOT / "index.html"
DATA_FILE = ROOT / "data" / "latest.json"
TZ = dt.timezone(dt.timedelta(hours=-4), name="America/St_Barthelemy")
LAT = float(os.getenv("NOVACTU_LAT", "17.90"))
LON = float(os.getenv("NOVACTU_LON", "-62.83"))

SARG_BADGES = {
    "impacte": "🔴 Impacté",
    "modere": "🟡 Modéré",
    "propre": "🟢 Propre",
}

DAYS_LONG = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
DAYS_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
MONTHS_LONG = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def log(message: str) -> None:
    now = dt.datetime.now(TZ).strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def http_get_json(url: str, timeout: int = 20) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "NovactuSBH/5.0 (+https://novactu.sbh)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        log(f"⚠ Source indisponible: {url[:90]} → {exc}")
        return None


def http_get_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "NovactuSBH/5.0 (+https://novactu.sbh)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        log(f"⚠ Source indisponible: {url[:90]} → {exc}")
        return ""


def build_url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode(params, doseq=True)


def wmo_label(code: int | None) -> tuple[str, str]:
    c = int(code or 2)
    if c == 0:
        return "☀️", "Ciel dégagé"
    if c <= 2:
        return "⛅", "Partiellement nuageux"
    if c == 3:
        return "☁️", "Couvert"
    if c <= 49:
        return "🌫", "Brouillard"
    if c <= 67:
        return "🌦", "Pluie possible"
    if c <= 82:
        return "🌦", "Averses éparses"
    return "⛈", "Orage"


def compass(deg: float | int | None) -> str:
    if deg is None:
        return "E"
    return ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][round(float(deg) / 45) % 8]


def safe_round(value: Any, default: float = 0, digits: int = 0) -> int | float:
    try:
        if value is None:
            return default
        result = round(float(value), digits)
        return int(result) if digits == 0 else result
    except Exception:
        return default


def fetch_weather() -> dict[str, Any] | None:
    log("🌤 Récupération météo Open-Meteo")
    url = build_url("https://api.open-meteo.com/v1/forecast", {
        "latitude": LAT,
        "longitude": LON,
        "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m", "wind_direction_10m"],
        "daily": ["temperature_2m_max", "temperature_2m_min", "weather_code", "wind_speed_10m_max", "precipitation_probability_max", "sunrise", "sunset"],
        "timezone": "America/St_Barthelemy",
        "forecast_days": 4,
    })
    data = http_get_json(url)
    if not data:
        return None
    current = data.get("current", {})
    daily = data.get("daily", {})
    days = []
    for i, day in enumerate(daily.get("time", [])[:3]):
        date = dt.date.fromisoformat(day)
        icon, cond = wmo_label((daily.get("weather_code") or [None])[i])
        days.append({
            "label": f"Aujourd'hui — {DAYS_LONG[date.weekday()]} {date.day} {MONTHS_LONG[date.month]}" if i == 0 else f"{DAYS_SHORT[date.weekday()]}. {date.day}",
            "tmax": safe_round((daily.get("temperature_2m_max") or [None])[i], 28),
            "tmin": safe_round((daily.get("temperature_2m_min") or [None])[i], 24),
            "icon": icon,
            "condition": cond,
            "wind": safe_round((daily.get("wind_speed_10m_max") or [None])[i], 25),
            "rain": safe_round((daily.get("precipitation_probability_max") or [None])[i], 30),
        })
    icon, cond = wmo_label(current.get("weather_code"))
    result = {
        "temp": safe_round(current.get("temperature_2m"), 27),
        "humidity": safe_round(current.get("relative_humidity_2m"), 75),
        "wind": safe_round(current.get("wind_speed_10m"), 25),
        "wind_dir": compass(current.get("wind_direction_10m")),
        "icon": icon,
        "condition": cond,
        "sunrise": (daily.get("sunrise") or ["05:40"])[0][-5:],
        "sunset": (daily.get("sunset") or ["18:35"])[0][-5:],
        "days": days,
    }
    return result


def fetch_marine() -> dict[str, Any] | None:
    log("🌊 Récupération mer / houle Open-Meteo Marine")
    url = build_url("https://marine-api.open-meteo.com/v1/marine", {
        "latitude": LAT,
        "longitude": LON,
        "daily": ["wave_height_max", "wave_period_max", "wave_direction_dominant", "sea_surface_temperature_max"],
        "timezone": "America/St_Barthelemy",
        "forecast_days": 2,
    })
    data = http_get_json(url)
    if not data:
        return None
    daily = data.get("daily", {})
    wave = safe_round((daily.get("wave_height_max") or [0.8])[0], 0.8, 1)
    period = safe_round((daily.get("wave_period_max") or [8])[0], 8)
    direction = compass((daily.get("wave_direction_dominant") or [90])[0])
    water = safe_round((daily.get("sea_surface_temperature_max") or [28])[0], 28)
    if wave >= 1.6:
        level = "Intermédiaire / Confirmé"
    elif wave >= 0.8:
        level = "Tous niveaux"
    else:
        level = "Débutants & paddle"
    return {"wave": wave, "period": period, "direction": direction, "water": water, "level": level}


def fetch_air_quality() -> dict[str, Any] | None:
    log("🌿 Récupération qualité air Open-Meteo")
    url = build_url("https://air-quality-api.open-meteo.com/v1/air-quality", {
        "latitude": LAT,
        "longitude": LON,
        "current": ["pm10", "pm2_5", "ozone", "dust"],
        "timezone": "America/St_Barthelemy",
        "forecast_days": 1,
    })
    data = http_get_json(url)
    if not data:
        return None
    current = data.get("current", {})
    pm25 = safe_round(current.get("pm2_5"), 15, 1)
    pm10 = safe_round(current.get("pm10"), 25, 1)
    ozone = safe_round(current.get("ozone"), 50, 1)
    dust = safe_round(current.get("dust"), 0, 1)
    score = max(float(pm25), float(pm10) * 0.55, float(dust) * 0.7)
    if score <= 25:
        label = "Bon"
    elif score <= 50:
        label = "Modéré"
    elif score <= 80:
        label = "Mauvais"
    else:
        label = "Très mauvais"
    if float(dust) > 100 or float(pm10) > 80:
        haze = "Épisode intense détecté"
        advice = "Évitez les efforts prolongés. Personnes sensibles : restez à l'intérieur."
    elif float(dust) > 50 or float(pm10) > 50:
        haze = "Épisode modéré détecté"
        advice = "Personnes sensibles : limitez l'exposition prolongée."
    else:
        haze = "Aucun épisode détecté"
        advice = "Activités extérieures libres. Idéal pour le sport et la plage."
    return {"iqa": int(round(score)), "label": label, "pm25": pm25, "pm10": pm10, "ozone": ozone, "dust": dust, "haze": haze, "advice": advice}


def fetch_sargassum() -> dict[str, Any]:
    """Best-effort local beach status. Uses public text when available + conservative seasonal heuristic."""
    log("🟤 Estimation sargasses")
    status = {
        "Grand-Cul-de-Sac": "modere",
        "Saint-Jean": "modere",
        "Lorient": "modere",
        "Gouverneur": "propre",
        "Colombier": "propre",
    }
    text_sources = [
        "https://www.journaldesaintbarth.com/fr/search/sargasses.html",
        "https://www.aoml.noaa.gov/phod/sargassum_inundation_report/",
    ]
    text = " ".join(http_get_text(url, timeout=12) for url in text_sources).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    keys = {
        "Grand-Cul-de-Sac": ["grand-cul-de-sac", "grand cul de sac", "gcds"],
        "Saint-Jean": ["saint-jean", "saint jean"],
        "Lorient": ["lorient"],
        "Gouverneur": ["gouverneur"],
        "Colombier": ["colombier"],
    }
    impact_words = ["invasion", "envahi", "échouage massif", "impacté", "massif", "fort"]
    moderate_words = ["arrivage", "présence", "modéré", "quelques", "signalé", "ramassage"]
    clean_words = ["propre", "aucune", "sans sargasse", "libre", "épargné", "dégagé"]
    for beach, aliases in keys.items():
        for alias in aliases:
            idx = text.find(alias)
            if idx < 0:
                continue
            ctx = text[max(0, idx - 250):idx + 450]
            if any(word in ctx for word in impact_words):
                status[beach] = "impacte"
                break
            if any(word in ctx for word in moderate_words):
                status[beach] = "modere"
                break
            if any(word in ctx for word in clean_words):
                status[beach] = "propre"
                break
    # Conservative seasonal correction for exposed coasts in May-Oct.
    if 5 <= dt.datetime.now(TZ).month <= 10:
        for beach in ["Grand-Cul-de-Sac", "Saint-Jean", "Lorient"]:
            if status[beach] == "propre":
                status[beach] = "modere"
    return status


def minutes_before(time_str: str, minutes: int = 60) -> str:
    hh, mm = map(int, time_str.split(":"))
    total = (hh * 60 + mm - minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def ferry_schedules(today: dt.datetime | None = None) -> dict[str, Any]:
    """Horaires départ Gustavia vers Saint-Martin.

    Voyager: valeurs relevées sur le système de réservation Voy12 pour la semaine fournie
    par Nicolas le 07/06/2026. À ce stade, on n'utilise pas les tarifs.
    Great Bay: grille fixe SBH -> Philipsburg, à vérifier périodiquement.
    """
    now = today or dt.datetime.now(TZ)
    weekday = now.weekday()  # lundi=0, dimanche=6

    voyager_by_weekday = {
        0: ["07:00", "10:15", "17:30"],
        1: ["07:25", "10:15", "17:30"],
        2: ["07:25", "10:15", "17:30"],
        3: ["07:25", "10:15", "17:30"],
        4: ["07:25", "10:15", "17:30"],
        5: ["07:25", "10:15", "17:30"],
        6: ["07:25", "10:15", "17:30"],
    }
    great_bay_by_weekday = {
        0: ["08:30", "11:00", "18:45"],
        1: ["08:30", "11:00", "18:45"],
        2: ["08:30", "11:00", "18:45"],
        3: ["08:30", "11:00", "18:45"],
        4: ["08:30", "11:00", "18:45"],
        5: ["08:30", "11:00", "18:45"],
        6: ["11:00", "18:45"],
    }
    return {
        "voyager": {
            "name": "Voyager",
            "route": "Gustavia → Marigot · côté français",
            "duration": "Durée ~1h · voy12.com",
            "times": voyager_by_weekday[weekday],
            "checkin_minutes": 60,
        },
        "great_bay": {
            "name": "Great Bay",
            "route": "Gustavia → Philipsburg · côté hollandais",
            "duration": "Durée ~45 min · Philipsburg",
            "times": great_bay_by_weekday[weekday],
            "checkin_minutes": 60,
        },
        "source_note": "Voyager: capture système réservation du 07/06/2026; Great Bay: planning public. Tarifs ignorés.",
    }


def ferry_rows(times: list[str], checkin_minutes: int = 60) -> str:
    rows = []
    for departure in times:
        checkin = minutes_before(departure, checkin_minutes)
        rows.append(
            '       <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;background:rgba(255,255,255,0.05);border-radius:4px;">\n'
            f'        <span style="font-family:\'Outfit\',sans-serif;font-size:17px;font-weight:800;color:#fff;">{departure}</span>\n'
            f'        <span style="font-size:8px;color:rgba(255,200,0,0.7);font-weight:600;">Check-in {checkin}</span>\n'
            '       </div>'
        )
    return "\n".join(rows)


def patch_ferry_card(html: str, company_label: str, times: list[str], checkin_minutes: int) -> str:
    rows = ferry_rows(times, checkin_minutes)
    pattern = (
        rf'(<!-- {re.escape(company_label)} -->.*?<!-- Horaires départ Gustavia -->\s*'
        r'<div style="display:flex;flex-direction:column;gap:6px;">)'
        r'.*?'
        r'(</div>\s*<div style="margin-top:8px;font-size:8px;color:rgba\(255,255,255,0\.25\);">)'
    )
    return re.sub(pattern, rf'\g<1>\n{rows}\n      \g<2>', html, count=1, flags=re.S)


def patch_great_bay_card(html: str, times: list[str], checkin_minutes: int) -> str:
    rows = ferry_rows(times, checkin_minutes)
    pattern = (
        r'(<!-- Great Bay -->.*?<div style="display:flex;flex-direction:column;gap:6px;">)'
        r'.*?'
        r'(</div>\s*<div style="margin-top:8px;font-size:8px;color:rgba\(255,255,255,0\.25\);">)'
    )
    return re.sub(pattern, rf'\g<1>\n{rows}\n      \g<2>', html, count=1, flags=re.S)


def date_labels() -> dict[str, str]:
    now = dt.datetime.now(TZ)
    d1 = now + dt.timedelta(days=1)
    d2 = now + dt.timedelta(days=2)
    return {
        "long": f"{DAYS_LONG[now.weekday()]} {now.day} {MONTHS_LONG[now.month]} {now.year}",
        "short": f"{now.day} {MONTHS_LONG[now.month]} {now.year}",
        "day0": f"{DAYS_LONG[now.weekday()]} {now.day} {MONTHS_LONG[now.month]}",
        "day1": f"{DAYS_SHORT[d1.weekday()]}. {d1.day}",
        "day2": f"{DAYS_SHORT[d2.weekday()]}. {d2.day}",
        "iso": now.isoformat(timespec="seconds"),
    }


def sub(pattern: str, repl: str, text: str, count: int = 0, flags: int = 0) -> str:
    return re.sub(pattern, repl, text, count=count, flags=flags)


def patch_html(raw_html: str, payload: dict[str, Any]) -> str:
    html = raw_html
    dates = payload["dates"]
    weather = payload.get("weather") or {}
    marine = payload.get("marine") or {}
    air = payload.get("air") or {}
    sarg = payload.get("sargassum") or {}
    ferries = payload.get("ferries") or {}

    html = sub(r'(<div class="wx-date-stamp">)[^<]*(</div>)', rf'\g<1>{dates["long"]}\g<2>', html)
    html = sub(r'(Conditions mer · )[^<]*(</div>)', rf'\g<1>{dates["short"]}\g<2>', html, count=1)
    html = sub(r'État des plages · [^<]+', f'État des plages · {dates["short"]}', html)
    html = sub(r'(Source · [^<]*? · )[^<]*?(</span>)', rf'\g<1>{dates["short"]}\g<2>', html, count=1)
    html = sub(r'(Navigation · Pêche · )[^<]+', rf'\g<1>{dates["short"]}', html)
    html = sub(r'(Prendre la mer · )[^<]+', rf'\g<1>{dates["short"]}', html)
    html = sub(r'(Conditions · )[^<]+( · Gustavia)', rf'\g<1>{dates["short"]}\g<2>', html)

    if weather:
        d = weather.get("days", [{}, {}, {}])
        html = sub(r'(<div class="wx-temp-big">)\d+(</div>)', rf'\g<1>{weather["temp"]}\g<2>', html, count=1)
        html = sub(r'(<div class="wx-cond">)[^<]*(</div>)', rf'\g<1>{weather["icon"]} {weather["condition"]}\g<2>', html, count=1)
        html = sub(r'(class="wx-s-val">)\d+%(</div><div class="wx-s-lbl">Humidité)', rf'\g<1>{weather["humidity"]}%\g<2>', html, count=1)
        html = sub(r'(class="wx-s-val">)[A-Z]{1,2} · \d+ km/h(</div><div class="wx-s-lbl">Vent)', rf'\g<1>{weather["wind_dir"]} · {weather["wind"]} km/h\g<2>', html, count=1)
        html = sub(r'(class="wx-s-val">)\d{2}:\d{2} · \d{2}:\d{2}(</div><div class="wx-s-lbl">Lever · Coucher)', rf'\g<1>{weather["sunrise"]} · {weather["sunset"]}\g<2>', html, count=1)
        for idx in range(min(3, len(d))):
            day = d[idx]
            html = sub(r'(<div class="wd-day">)[^<]*(</div>)', rf'\g<1>{day["label"]}\g<2>', html, count=1)
            html = sub(r'(<div class="wd-icon">)[^<]*(</div>)', rf'\g<1>{day["icon"]}\g<2>', html, count=1)
            html = sub(r'(<div class="wd-temp">)\d+(°</div>)', rf'\g<1>{day["tmax"]}\g<2>', html, count=1)
            html = sub(r'(<div class="wd-range">)\d+° · \d+°(</div>)', rf'\g<1>{day["tmin"]}° · {day["tmax"]}°\g<2>', html, count=1)
            html = sub(r'(<div class="wd-wind">)[^<]*(</div>)', rf'\g<1>{weather["wind_dir"]} {day["wind"]} km/h<br>{day["condition"]}\g<2>', html, count=1)

    if marine:
        html = sub(r'(<div class="surf-hook">).*?(</div>)', rf'\g<1>Eau à {marine["water"]}°C, houle de {marine["wave"]}m — {marine["level"].lower()}. Conditions à vérifier sur place avant la mise à l’eau.\g<2>', html, count=1, flags=re.S)
        html = sub(r'(Vagues</span><span class="ss-val">|Vagues</span><span><span class="ss-val">)~?[\d.]+\s*m?', rf'\g<1>~{marine["wave"]} m', html, count=1)
        html = sub(r'(Température eau</span><span class="ss-val">|Température eau</span><span><span class="ss-val">)\d+(°)', rf'\g<1>{marine["water"]}\g<2>', html, count=1)
        html = sub(r'(Niveau conseillé</span><span class="ss-val">|Niveau conseillé</span><span><span class="ss-val">)[^<]*(</span>)', rf'\g<1>{marine["level"]}\g<2>', html, count=1)
        html = sub(r'(Direction</span><span class="ss-val">|Direction</span><span><span class="ss-val">)[^<]*(</span>)', rf'\g<1>{marine["direction"]}\g<2>', html, count=1)
        html = sub(r'(class="wx-s-val">)\d+°C(</div><div class="wx-s-lbl">Eau)', rf'\g<1>{marine["water"]}°C\g<2>', html, count=1)
        # Prendre la mer : confort traversée basé sur la houle marine.
        wave = float(marine.get("wave", 0) or 0)
        sea_badge = "⚠ Mer agitée" if wave >= 1.3 else "Mer correcte"
        crossing_text = "Traversée agitée possible." if wave >= 1.3 else "Traversée généralement correcte."
        html = sub(r'(<span style="font-size:9px;font-weight:800;letter-spacing:0\.1em;text-transform:uppercase;color:#ffc800;">)[^<]*(</span>)', rf'\g<1>{sea_badge}\g<2>', html, count=1)
        html = sub(r'<span style="color:#fff;font-weight:600;">Houle [^<]+</span> — [^<]+<br>', f'<span style="color:#fff;font-weight:600;">Houle {marine["wave"]}m</span> — {crossing_text}<br>', html, count=1)

    if ferries:
        voyager = ferries.get("voyager") or {}
        great_bay = ferries.get("great_bay") or {}
        html = patch_ferry_card(html, "Voyager", voyager.get("times", []), int(voyager.get("checkin_minutes", 60)))
        html = patch_great_bay_card(html, great_bay.get("times", []), int(great_bay.get("checkin_minutes", 60)))

    if air:
        html = sub(r'(font-size:32px;font-weight:800;color:#[^;]+;line-height:1;">)\d+(</span>)', rf'\g<1>{air["iqa"]}\g<2>', html, count=1)
        html = sub(r'(font-family:\'Outfit\',sans-serif;font-size:32px;font-weight:700;color:#fff;line-height:1;margin-bottom:8px;">)(Bon|Modéré|Mauvais|Très mauvais)(</div>)', rf'\g<1>{air["label"]}\g<3>', html, count=1)
        html = sub(r'PM2\.5 &nbsp;·&nbsp; [\d.]+ µg/m³', f'PM2.5 &nbsp;·&nbsp; {air["pm25"]} µg/m³', html)
        html = sub(r'PM10 &nbsp;·&nbsp; [\d.]+ µg/m³', f'PM10 &nbsp;·&nbsp; {air["pm10"]} µg/m³', html)
        html = sub(r'Ozone O₃ &nbsp;·&nbsp; [\d.]+ µg/m³', f'Ozone O₃ &nbsp;·&nbsp; {air["ozone"]} µg/m³', html)
        html = sub(r'(Aucun épisode détecté|Épisode modéré détecté|Épisode intense détecté)', air["haze"], html, count=1)
        html = sub(r'(Activités extérieures libres\.[^<]+|Personnes sensibles[^<]+|Évitez les efforts[^<]+|Brume saharienne active\.[^<]+)', air["advice"], html, count=1)

    for beach, state in sarg.items():
        badge = SARG_BADGES.get(state, "🟡 Modéré")
        pattern = rf'(<div style="font-size:14px;font-weight:600;color:#fff;">{re.escape(beach)}</div>.*?<span style="[^"]*white-space:nowrap;">)[^<]*(</span>)'
        html = sub(pattern, rf'\g<1>{html_lib.escape(badge)}\g<2>', html, flags=re.S)

    marker = "<!-- NOVACTU_DATA -->"
    data_script = f'{marker}\n<script id="novactu-data" type="application/json">{json.dumps(payload, ensure_ascii=False)}</script>'
    if marker in html:
        html = re.sub(r'<!-- NOVACTU_DATA -->\s*<script id="novactu-data" type="application/json">.*?</script>', data_script, html, flags=re.S)
    else:
        html = html.replace("</body>", data_script + "\n</body>")
    return html


def main() -> int:
    log("NOVACTU SBH — mise à jour")
    if not TARGET_FILE.exists():
        log(f"❌ {TARGET_FILE.name} introuvable")
        return 1
    payload = {
        "generated_at": dt.datetime.now(TZ).isoformat(timespec="seconds"),
        "coordinates": {"latitude": LAT, "longitude": LON},
        "dates": date_labels(),
        "sources": [
            "Open-Meteo Forecast API",
            "Open-Meteo Marine API",
            "Open-Meteo Air Quality API",
            "NOAA/AOML Sargassum Inundation Report + Journal de Saint-Barth search when reachable",
            "Voyager schedule manually captured from booking system on 2026-06-07; Great Bay public schedule",
        ],
        "weather": fetch_weather(),
        "marine": fetch_marine(),
        "air": fetch_air_quality(),
        "sargassum": fetch_sargassum(),
        "ferries": ferry_schedules(),
    }
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html = TARGET_FILE.read_text(encoding="utf-8")
    TARGET_FILE.write_text(patch_html(html, payload), encoding="utf-8")
    log("✅ index.html et data/latest.json mis à jour")
    return 0


if __name__ == "__main__":
    sys.exit(main())
