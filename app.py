"""Streamlit weather dashboard for Ecowitt WS90 + WH31 sensors (rtl_433 via MQTT).

Run:
    streamlit run app.py                         # uses ./config.yaml
    streamlit run app.py -- --config other.yaml
    WEATHER_CONFIG=other.yaml streamlit run app.py
"""

from __future__ import annotations

import argparse
import hmac
import math
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from mqtt_hub import MqttHub, SensorConf


# ============================================================ configuration
def config_path() -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=os.environ.get("WEATHER_CONFIG", "config.yaml"))
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args.config


@st.cache_resource
def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["dashboard"] = cfg.get("dashboard") or {}
    cfg["wh31"] = cfg.get("wh31") or []
    return cfg


def build_sensors(cfg: dict) -> list[SensorConf]:
    sensors = []
    if cfg.get("ws90"):
        w = cfg["ws90"]
        sensors.append(SensorConf(
            key="ws90", name=w.get("name", "Outdoor"), kind="ws90",
            host=w["host"], port=int(w.get("port", 1883)), topic=w["topic"].rstrip("/"),
            username=w.get("username"), password=w.get("password"),
        ))
    for i, s in enumerate(cfg["wh31"]):
        sensors.append(SensorConf(
            key=f"wh31_{i}", name=s.get("name", f"Sensor {i + 1}"), kind="wh31",
            host=s["host"], port=int(s.get("port", 1883)), topic=s["topic"].rstrip("/"),
            username=s.get("username"), password=s.get("password"),
        ))
    return sensors


@st.cache_resource
def get_hub(path: str) -> MqttHub:
    cfg = load_config(path)
    d = cfg["dashboard"]
    return MqttHub(build_sensors(cfg), d.get("history_db", "weather_history.sqlite"),
                   int(d.get("sample_seconds", 60)))


CFG_PATH = config_path()
CFG = load_config(CFG_PATH)
DASH = CFG["dashboard"]
LANG = str(DASH.get("language", "en")).lower()[:2]
if LANG not in ("it", "en"):
    LANG = "en"
TZ = ZoneInfo(DASH.get("timezone", "Europe/Rome"))
STALE = int(DASH.get("stale_seconds", 600))
WIND_UNIT = DASH.get("wind_unit", "km/h")
# Dashboard password: top-level "password" key (or dashboard.password)
PASSWORD = CFG.get("password") or DASH.get("password")

st.set_page_config(page_title=DASH.get("title", "Weather"), page_icon="🌦️", layout="wide")


# ============================================================ translations
TEXT = {
    "it": {
        "default_title": "Meteo", "outdoor": "Esterno", "temperature": "Temperatura",
        "feels_like": "Percepita", "dew_point": "Punto di rugiada", "humidity": "Umidità",
        "minmax_today": "Min / Max oggi", "wind": "Vento", "gust": "Raffica",
        "max_gust_today": "Raffica max oggi", "direction": "Direzione", "rain": "Pioggia",
        "last_hour": "Ultima ora", "today": "Oggi", "last_24h": "Ultime 24h",
        "week": "Settimana", "month": "Mese", "year": "Anno", "solar_uv": "Solare e UV",
        "brightness": "Luminosità", "max_today": "Max oggi", "uv_index": "Indice UV",
        "station_status": "Stato stazione", "battery": "Batteria",
        "battery_voltage": "Tensione batteria", "supercap": "Supercondensatore",
        "last_data": "Ultimo dato", "rooms": "Temperatura e umidità ambienti",
        "channel_id": "Canale / ID", "low": "Bassa", "never": "mai", "s_ago": "{}s fa",
        "min_ago": "{} min fa", "h_ago": "{} h fa", "waiting": "In attesa dei primi dati MQTT…",
        "charts": "Grafici", "history_empty": "Storico ancora vuoto: i grafici compariranno "
        "dopo i primi campioni (uno ogni {} s).", "dew": "Rugiada", "average": "Medio",
        "wind_direction": "Direzione del vento", "mm_hour": "mm/ora", "cumulative": "Cumulata",
        "mm_cumulative": "mm cumulati", "solar_radiation_uv": "Radiazione solare e UV",
        "solar": "Solare", "rooms_temp": "Ambienti: temperatura",
        "rooms_hum": "Ambienti: umidità", "password": "Password", "login": "Accedi",
        "wrong_password": "Password errata", "login_title": "Accesso alla dashboard",
        "connecting": "connessione…", "connected": "connesso", "disconnected": "disconnesso",
        "error": "errore",
        "uv": ["Basso", "Moderato", "Alto", "Molto alto", "Estremo"],
        "beaufort": ["Calma", "Bava di vento", "Brezza leggera", "Brezza tesa",
                     "Vento moderato", "Vento teso", "Vento fresco", "Vento forte",
                     "Burrasca moderata", "Burrasca forte", "Tempesta", "Fortunale", "Uragano"],
        "dirs": ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"],
        "date_fmt": "%d/%m/%Y %H:%M:%S", "short_date_fmt": "%d/%m %H:%M:%S",
    },
    "en": {
        "default_title": "Weather", "outdoor": "Outdoor", "temperature": "Temperature",
        "feels_like": "Feels like", "dew_point": "Dew point", "humidity": "Humidity",
        "minmax_today": "Min / Max today", "wind": "Wind", "gust": "Gust",
        "max_gust_today": "Max gust today", "direction": "Direction", "rain": "Rainfall",
        "last_hour": "Last hour", "today": "Today", "last_24h": "Last 24h",
        "week": "Week", "month": "Month", "year": "Year", "solar_uv": "Solar & UV",
        "brightness": "Brightness", "max_today": "Max today", "uv_index": "UV index",
        "station_status": "Station status", "battery": "Battery",
        "battery_voltage": "Battery voltage", "supercap": "Supercapacitor",
        "last_data": "Last data", "rooms": "Indoor temperature & humidity",
        "channel_id": "Channel / ID", "low": "Low", "never": "never", "s_ago": "{}s ago",
        "min_ago": "{} min ago", "h_ago": "{} h ago", "waiting": "Waiting for the first MQTT data…",
        "charts": "Charts", "history_empty": "History is still empty: charts will appear "
        "after the first samples (one every {} s).", "dew": "Dew point", "average": "Average",
        "wind_direction": "Wind direction", "mm_hour": "mm/hour", "cumulative": "Cumulative",
        "mm_cumulative": "cumulative mm", "solar_radiation_uv": "Solar radiation & UV",
        "solar": "Solar", "rooms_temp": "Indoor: temperature",
        "rooms_hum": "Indoor: humidity", "password": "Password", "login": "Log in",
        "wrong_password": "Wrong password", "login_title": "Dashboard login",
        "connecting": "connecting…", "connected": "connected", "disconnected": "disconnected",
        "error": "error",
        "uv": ["Low", "Moderate", "High", "Very high", "Extreme"],
        "beaufort": ["Calm", "Light air", "Light breeze", "Gentle breeze", "Moderate breeze",
                     "Fresh breeze", "Strong breeze", "Near gale", "Gale", "Strong gale",
                     "Storm", "Violent storm", "Hurricane"],
        "dirs": ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"],
        "date_fmt": "%Y-%m-%d %H:%M:%S", "short_date_fmt": "%m-%d %H:%M:%S",
    },
}


def tr(key: str, *args):
    s = TEXT[LANG][key]
    return s.format(*args) if args else s


# ============================================================ password gate
def require_password():
    """If a password is configured, ask for it once per browser session."""
    if not PASSWORD or st.session_state.get("authenticated"):
        return
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        st.markdown(f"### {DASH.get('title', tr('default_title'))}")
        st.caption(tr("login_title"))
        with st.form("login"):
            pwd = st.text_input(tr("password"), type="password")
            ok = st.form_submit_button(tr("login"), width="stretch")
        if ok:
            if hmac.compare_digest(pwd.encode(), str(PASSWORD).encode()):
                st.session_state["authenticated"] = True
                st.rerun()
            st.error(tr("wrong_password"))
    st.stop()


require_password()

HUB = get_hub(CFG_PATH)
SENSORS = build_sensors(CFG)


# ============================================================ weather math
def dew_point(t, rh):
    """Dew point (Magnus formula)."""
    if t is None or not rh:
        return None
    a, b = 17.62, 243.12
    g = math.log(rh / 100.0) + a * t / (b + t)
    return b * g / (a - g)


def feels_like(t, rh, wind_ms):
    """Wind chill (T<=10°C, wind>4.8 km/h), heat index (T>=26.7°C), otherwise T."""
    if t is None:
        return None
    v = (wind_ms or 0) * 3.6
    if t <= 10 and v > 4.8:
        return 13.12 + 0.6215 * t - 11.37 * v ** 0.16 + 0.3965 * t * v ** 0.16
    if t >= 26.7 and rh is not None:
        f = t * 9 / 5 + 32
        hi = (-42.379 + 2.04901523 * f + 10.14333127 * rh - 0.22475541 * f * rh
              - 6.83783e-3 * f * f - 5.481717e-2 * rh * rh + 1.22874e-3 * f * f * rh
              + 8.5282e-4 * f * rh * rh - 1.99e-6 * f * f * rh * rh)
        return (hi - 32) * 5 / 9
    return t


# Upper limits (m/s) of Beaufort scale levels 0..11; above the last one is 12
BEAUFORT_LIMITS = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]


def beaufort(ms):
    n = next((i for i, lim in enumerate(BEAUFORT_LIMITS) if (ms or 0) < lim), 12)
    return n, tr("beaufort")[n]


def cardinal(deg):
    return tr("dirs")[int((deg % 360) / 22.5 + 0.5) % 16] if deg is not None else "--"


def uv_level(uvi):
    if uvi is None:
        return "--", "#999"
    colors = ["#4caf50", "#fbc02d", "#fb8c00", "#e53935", "#8e24aa"]
    i = next((i for i, lim in enumerate([3, 6, 8, 11]) if uvi < lim), 4)
    return tr("uv")[i], colors[i]


def wind(ms):
    if ms is None:
        return None
    return ms * 3.6 if WIND_UNIT == "km/h" else ms


def fmt(v, nd=1, unit=""):
    if v is None:
        return "--"
    return f"{v:.{nd}f}{unit}"


def ago(ts):
    if ts is None:
        return tr("never")
    s = int(time.time() - ts)
    if s < 60:
        return tr("s_ago", s)
    if s < 3600:
        return tr("min_ago", s // 60)
    return tr("h_ago", s // 3600)


# ============================================================ history
def period_starts(now: datetime) -> dict[str, float]:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "last_hour": (now - timedelta(hours=1)).timestamp(),
        "today": midnight.timestamp(),
        "last_24h": (now - timedelta(hours=24)).timestamp(),
        "week": (midnight - timedelta(days=midnight.weekday())).timestamp(),
        "month": midnight.replace(day=1).timestamp(),
        "year": midnight.replace(month=1, day=1).timestamp(),
    }


def rain_since(current, since_ts):
    """Rain since a timestamp, from the cumulative rain_mm counter."""
    if current is None:
        return None
    first = HUB.first_value_since("ws90", "rain_mm", since_ts)
    if first is None:
        return None
    return max(0.0, current - first)


@st.cache_data(ttl=60, show_spinner=False)
def load_history(hours: float, _bucket: int) -> pd.DataFrame:
    rows = HUB.history([s.key for s in SENSORS], time.time() - hours * 3600)
    df = pd.DataFrame(rows, columns=["ts", "sensor", "field", "value"])
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert(TZ)
    return df


def series(df, sensor, fname):
    if df.empty:
        return pd.Series(dtype=float)
    d = df[(df.sensor == sensor) & (df.field == fname)]
    return pd.Series(d["value"].values, index=pd.DatetimeIndex(d["time"]))


# ============================================================ UI: style
CSS = """
<style>
.block-container {padding-top: 3rem; max-width: 1500px;}
.ew-head {display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap;
  gap:8px; margin-bottom: 12px;}
.ew-head h1 {font-size: 1.7rem; margin:0; color:#1f2d3d; padding:0;}
.ew-head .sub {color:#6b7a8c; font-size: .9rem;}
.ew-grid {display:grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap:14px;}
.ew-card {background:#fff; border-radius:12px; box-shadow:0 1px 4px rgba(20,40,80,.08);
  padding:14px 16px; display:flex; flex-direction:column; gap:6px; min-height:170px;}
.ew-card .title {display:flex; align-items:center; gap:8px; font-weight:600; color:#334;
  font-size:.95rem; border-bottom:1px solid #eef1f5; padding-bottom:6px;}
.ew-card .title .ic {width:26px; height:26px; border-radius:7px; display:flex;
  align-items:center; justify-content:center; font-size:15px; color:#fff;}
.ew-card .title .when {margin-left:auto; font-weight:400; font-size:.75rem; color:#99a;}
.ew-card .title .when.stale {color:#e53935; font-weight:600;}
.ew-big {font-size:2.5rem; font-weight:300; color:#1f2d3d; line-height:1.1;}
.ew-big small {font-size:1rem; color:#6b7a8c; margin-left:2px;}
.ew-row {display:flex; justify-content:space-between; font-size:.85rem; color:#556;
  border-bottom:1px dashed #f0f2f5; padding:2px 0;}
.ew-row b {color:#1f2d3d; font-weight:600; white-space:nowrap; text-align:right;}
.ew-row span {white-space:nowrap; margin-right:8px;}
.ew-flex {display:flex; gap:14px; align-items:center;}
.ew-flex > div {flex:1;}
.ew-badge {display:inline-block; padding:1px 8px; border-radius:10px; color:#fff;
  font-size:.75rem; font-weight:600;}
.ew-section {font-size:1.1rem; font-weight:600; color:#334; margin:18px 0 8px 0;}
.ew-ch .ew-big {font-size:2rem;}
.ew-bat-ok {color:#43a047;} .ew-bat-low {color:#e53935;}
</style>
"""

COLORS = {"temp": "#f4511e", "wind": "#26a69a", "rain": "#1e88e5", "sun": "#fbc02d",
          "uv": "#8e24aa", "bat": "#546e7a", "ch": "#5c6bc0"}


def card(title, icon, color, body, updated=None, extra_cls=""):
    stale = updated is None or time.time() - updated > STALE
    when = f'<span class="when{" stale" if stale else ""}">{ago(updated)}</span>'
    return (f'<div class="ew-card {extra_cls}"><div class="title">'
            f'<span class="ic" style="background:{color}">{icon}</span>{title}{when}</div>'
            f'{body}</div>')


def row(label, value):
    return f'<div class="ew-row"><span>{label}</span><b>{value}</b></div>'


def compass_svg(deg, size=120):
    c = size / 2
    r = c - 8
    ticks = ""
    for i in range(0, 360, 30):
        a = math.radians(i)
        x1, y1 = c + (r - 6) * math.sin(a), c - (r - 6) * math.cos(a)
        x2, y2 = c + r * math.sin(a), c - r * math.cos(a)
        ticks += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#c5ccd6" stroke-width="2"/>'
    dirs = tr("dirs")
    labels = "".join(
        f'<text x="{c + (r - 17) * math.sin(math.radians(a)):.1f}" '
        f'y="{c - (r - 17) * math.cos(math.radians(a)) + 4:.1f}" font-size="11" '
        f'text-anchor="middle" fill="#6b7a8c" font-weight="600">{t}</text>'
        for a, t in [(0, dirs[0]), (90, dirs[4]), (180, dirs[8]), (270, dirs[12])])
    arrow = ""
    if deg is not None:
        # the arrow points where the wind blows to (wind direction + 180°)
        arrow = (f'<g transform="rotate({deg} {c} {c})">'
                 f'<polygon points="{c},{c + r - 4} {c - 8},{c + r - 22} {c + 8},{c + r - 22}" fill="{COLORS["wind"]}"/>'
                 f'<line x1="{c}" y1="{c - r + 8}" x2="{c}" y2="{c + r - 20}" stroke="{COLORS["wind"]}" stroke-width="3"/>'
                 f'<circle cx="{c}" cy="{c - r + 8}" r="4" fill="{COLORS["wind"]}"/></g>')
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="#f7f9fc" stroke="#dde3ea" stroke-width="2"/>'
            f'{ticks}{labels}{arrow}</svg>')


def battery_html(ok):
    if ok is None:
        return "--"
    if isinstance(ok, (int, float)) and 0 < ok < 1:
        cls = "ew-bat-ok" if ok >= 0.3 else "ew-bat-low"
        return f'<span class="{cls}">{ok * 100:.0f}%</span>'
    return '<span class="ew-bat-ok">OK</span>' if ok else f'<span class="ew-bat-low">{tr("low")}</span>'


def ws_name():
    return CFG.get("ws90", {}).get("name", tr("outdoor"))


# ============================================================ UI: sections
def render_cards(snap):
    now = datetime.now(TZ)
    starts = period_starts(now)
    html = []

    ws = snap.get("ws90")
    if ws is not None:
        v, upd = ws.values, ws.updated
        t, rh = v.get("temperature_C"), v.get("humidity")
        avg, gust, wdir = v.get("wind_avg_m_s"), v.get("wind_max_m_s"), v.get("wind_dir_deg")

        tmin, tmax = HUB.minmax_since("ws90", "temperature_C", starts["today"])
        body = (f'<div class="ew-big">{fmt(t)}<small>°C</small></div>'
                + row(tr("feels_like"), fmt(feels_like(t, rh, avg), 1, " °C"))
                + row(tr("dew_point"), fmt(dew_point(t, rh), 1, " °C"))
                + row(tr("humidity"), fmt(rh, 0, " %"))
                + row(tr("minmax_today"), f"{fmt(tmin)} / {fmt(tmax)} °C"))
        html.append(card(f"{ws_name()} · {tr('temperature')}", "🌡", COLORS["temp"], body, upd))

        bn, bname = beaufort(avg)
        _, gmax = HUB.minmax_since("ws90", "wind_max_m_s", starts["today"])
        body = (f'<div class="ew-flex"><div>'
                f'<div class="ew-big">{fmt(wind(avg))}<small>{WIND_UNIT}</small></div>'
                + row(tr("gust"), fmt(wind(gust), 1, f" {WIND_UNIT}"))
                + row(tr("max_gust_today"), fmt(wind(gmax), 1, f" {WIND_UNIT}"))
                + row(tr("direction"), f"{cardinal(wdir)} {fmt(wdir, 0, '°')}")
                + row("Beaufort", f"{bn}")
                + f'</div><div style="flex:0 0 100px">{compass_svg(wdir, 100)}</div></div>'
                + f'<div style="font-size:.8rem;color:#6b7a8c">{bname}</div>')
        html.append(card(tr("wind"), "💨", COLORS["wind"], body, upd))

        rain = v.get("rain_mm")
        r10 = rain_since(rain, time.time() - 600)
        rate = r10 * 6 if r10 is not None else None
        body = (f'<div class="ew-big">{fmt(rate)}<small>mm/h</small></div>'
                + "".join(row(tr(k), fmt(rain_since(rain, ts), 1, " mm")) for k, ts in starts.items()))
        html.append(card(tr("rain"), "🌧", COLORS["rain"], body, upd))

        # W/m² estimated from lux with the usual Ecowitt factor (126.7 lux = 1 W/m²)
        lux, uvi = v.get("light_lux"), v.get("uvi")
        uvn, uvc = uv_level(uvi)
        _, smax = HUB.minmax_since("ws90", "light_lux", starts["today"])
        body = (f'<div class="ew-big">{fmt(lux / 126.7 if lux is not None else None)}'
                f'<small>W/m²</small></div>'
                + row(tr("brightness"), fmt(lux, 0, " lux"))
                + row(tr("max_today"), fmt(smax / 126.7 if smax is not None else None, 1, " W/m²"))
                + row(tr("uv_index"), f'{fmt(uvi, 0)} <span class="ew-badge" style="background:{uvc}">{uvn}</span>'))
        html.append(card(tr("solar_uv"), "☀️", COLORS["sun"], body, upd))

        mv = v.get("battery_mV")
        body = (row(tr("battery"), battery_html(v.get("battery_ok")))
                + row(tr("battery_voltage"), fmt(mv / 1000 if mv else None, 2, " V"))
                + row(tr("supercap"), fmt(v.get("supercap_V"), 1, " V"))
                + row("Firmware", v.get("firmware", "--"))
                + row("ID", v.get("id", "--"))
                + row(tr("last_data"), datetime.fromtimestamp(upd, TZ).strftime(tr("short_date_fmt")) if upd else "--"))
        html.append(card(tr("station_status"), "🔋", COLORS["bat"], body, upd))

    st.markdown(f'<div class="ew-grid">{"".join(html)}</div>', unsafe_allow_html=True)

    chans = [s for s in SENSORS if s.kind == "wh31"]
    if chans:
        st.markdown(f'<div class="ew-section">{tr("rooms")}</div>', unsafe_allow_html=True)
        html = []
        for s in chans:
            stt = snap[s.key]
            v = stt.values
            t, rh = v.get("temperature_C"), v.get("humidity")
            body = (f'<div class="ew-flex"><div><div class="ew-big">{fmt(t)}<small>°C</small></div></div>'
                    f'<div><div class="ew-big">{fmt(rh, 0)}<small>%</small></div></div></div>'
                    + row(tr("dew_point"), fmt(dew_point(t, rh), 1, " °C"))
                    + row(tr("battery"), battery_html(v.get("battery_ok")))
                    + row(tr("channel_id"), f'{v.get("channel", "--")} / {v.get("id", "--")}'))
            html.append(card(s.name, "🏠", COLORS["ch"], body, stt.updated, "ew-ch"))
        st.markdown(f'<div class="ew-grid">{"".join(html)}</div>', unsafe_allow_html=True)


def fig_base(title, ytitle):
    fig = go.Figure()
    fig.update_layout(title=title, height=320, margin=dict(l=10, r=10, t=40, b=10),
                      paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                      legend=dict(orientation="h", y=-0.15), hovermode="x unified",
                      yaxis_title=ytitle)
    fig.update_xaxes(gridcolor="#eef1f5")
    fig.update_yaxes(gridcolor="#eef1f5")
    return fig


def render_charts():
    hours = float(DASH.get("chart_hours", 24))
    df = load_history(hours, int(time.time() // 60))
    if df.empty:
        st.info(tr("history_empty", DASH.get("sample_seconds", 60)))
        return

    c1, c2 = st.columns(2)
    if CFG.get("ws90"):
        t = series(df, "ws90", "temperature_C")
        rh = series(df, "ws90", "humidity")
        fig = fig_base(f"{ws_name()}: {tr('temperature').lower()}", "°C")
        fig.add_scatter(x=t.index, y=t.values, name=tr("temperature"), line=dict(color=COLORS["temp"]))
        if not rh.empty:
            dp = [dew_point(a, b) for a, b in zip(t.values, rh.reindex(t.index).values)]
            fig.add_scatter(x=t.index, y=dp, name=tr("dew"), line=dict(color="#1e88e5", dash="dot"))
        c1.plotly_chart(fig, width="stretch")

        fig = fig_base(f"{ws_name()}: {tr('humidity').lower()}", "%")
        fig.add_scatter(x=rh.index, y=rh.values, name=tr("humidity"), line=dict(color="#00897b"))
        c2.plotly_chart(fig, width="stretch")

        k = 3.6 if WIND_UNIT == "km/h" else 1
        a, g = series(df, "ws90", "wind_avg_m_s") * k, series(df, "ws90", "wind_max_m_s") * k
        fig = fig_base(tr("wind"), WIND_UNIT)
        fig.add_scatter(x=a.index, y=a.values, name=tr("average"), line=dict(color=COLORS["wind"]))
        fig.add_scatter(x=g.index, y=g.values, name=tr("gust"), line=dict(color="#ef6c00", width=1))
        c1.plotly_chart(fig, width="stretch")

        d = series(df, "ws90", "wind_dir_deg")
        dirs = tr("dirs")
        fig = fig_base(tr("wind_direction"), "°")
        fig.add_scatter(x=d.index, y=d.values, mode="markers", name=tr("direction"),
                        marker=dict(color=COLORS["wind"], size=4))
        fig.update_yaxes(range=[0, 360], tickvals=[0, 90, 180, 270, 360],
                         ticktext=[dirs[0], dirs[4], dirs[8], dirs[12], dirs[0]])
        c2.plotly_chart(fig, width="stretch")

        r = series(df, "ws90", "rain_mm")
        if not r.empty:
            inc = r.diff().clip(lower=0).fillna(0)
            hourly = inc.groupby(pd.DatetimeIndex(inc.index).floor("h")).sum()
            fig = fig_base(tr("rain"), "mm")
            fig.add_bar(x=hourly.index, y=hourly.values, name=tr("mm_hour"), marker_color=COLORS["rain"])
            fig.add_scatter(x=inc.index, y=inc.cumsum().values, name=tr("cumulative"), yaxis="y2",
                            line=dict(color="#0d47a1"))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", title=tr("mm_cumulative")))
            c1.plotly_chart(fig, width="stretch")

        lux, uv = series(df, "ws90", "light_lux"), series(df, "ws90", "uvi")
        fig = fig_base(tr("solar_radiation_uv"), "W/m²")
        fig.add_scatter(x=lux.index, y=lux.values / 126.7, name=tr("solar"), fill="tozeroy",
                        line=dict(color=COLORS["sun"]))
        fig.add_scatter(x=uv.index, y=uv.values, name="UVI", yaxis="y2", line=dict(color=COLORS["uv"]))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", title="UVI"))
        c2.plotly_chart(fig, width="stretch")

    chans = [s for s in SENSORS if s.kind == "wh31"]
    if chans:
        c1, c2 = st.columns(2)
        ft = fig_base(tr("rooms_temp"), "°C")
        fh = fig_base(tr("rooms_hum"), "%")
        for s in chans:
            t, h = series(df, s.key, "temperature_C"), series(df, s.key, "humidity")
            ft.add_scatter(x=t.index, y=t.values, name=s.name)
            fh.add_scatter(x=h.index, y=h.values, name=s.name)
        c1.plotly_chart(ft, width="stretch")
        c2.plotly_chart(fh, width="stretch")


def broker_text():
    parts = []
    for broker, (code, detail) in HUB.broker_status.items():
        txt = tr(code)
        parts.append(f"{broker}: {txt}" + (f" ({detail})" if detail else ""))
    return " · ".join(parts)


# ============================================================ page
st.markdown(CSS, unsafe_allow_html=True)


@st.fragment(run_every=int(DASH.get("refresh_seconds", 10)))
def live():
    snap = HUB.snapshot()
    st.markdown(
        f'<div class="ew-head"><h1>{DASH.get("title", tr("default_title"))}</h1>'
        f'<div class="sub">{datetime.now(TZ).strftime(tr("date_fmt"))} · MQTT {broker_text()}</div></div>',
        unsafe_allow_html=True)
    if all(s.updated is None for s in snap.values()):
        st.info(tr("waiting"))
    render_cards(snap)


live()

st.markdown(f'<div class="ew-section">{tr("charts")}</div>', unsafe_allow_html=True)


@st.fragment(run_every=60)
def charts():
    render_charts()


charts()
