import os
import base64
import time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from textwrap import dedent

# ── Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="THI PV Modules",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_API_BASE = "http://localhost:5000"
GREEN = "#63B686"
PURPLE = "#7E57C2"

TEXT = {
    "en": {
        "title": "THI Photovoltaic Module Monitor",
        "thi_photovoltaics": "THI Photovoltaics",
        "last_updated": "Last updated",
        "lifetime_kpis": "LIFETIME KEY METRICS",
        "production": "Production",
        "reclaimed": "Reclaimed energy",
        "equiv": "LIFETIME ENERGY EQUIVALENTS",
        "vehicles": "Vehicles",
        "trees": "Trees",
        "co2": "CO₂",
        "kettles": "Kettles",
        "income": "Income equivalent",
        "controls": "Controls",
        "pv_generation": "PV Generation",
        "consumption": "Consumption",
        "net": "Net",
        "no_data": "No data available",
        "battery_charge": "Battery charge (%)",
        "api_error": "Failed to fetch data",
        "historical_none": "No historical readings for this selection.",
        "api_base": "API base URL",
        "kiosk_on": "Enter Display Mode",
        "kiosk_off": "Exit Display Mode",
        "lang": "Language",
        "time_window": "Time window",
        "day": "Day",
        "week": "Week",
        "month": "Month",
        "year": "Year",
        "slide": "Slideshow (alternate EN/DE)",
        "avg": "Average",
    },
    "de": {
        "title": "THI Photovoltaik-Modulmonitor",
        "thi_photovoltaics": "THI-Photovoltaik",
        "last_updated": "Zuletzt aktualisiert",
        "lifetime_kpis": "KENNZAHLEN (GESAMT)",
        "production": "Erzeugung",
        "reclaimed": "Zurückgewonnene Energie",
        "income": "Ertragsäquivalent",
        "equiv": "ENERGIEÄQUIVALENTE (GESAMT)",
        "vehicles": "Fahrzeuge",
        "trees": "Bäume",
        "co2": "CO₂",
        "kettles": "Wasserkocher",
        "controls": "Steuerung",
        "pv_generation": "PV-Erzeugung",
        "consumption": "Verbrauch",
        "net": "Saldo",
        "battery_charge": "Batterieladung (%)",
        "no_data": "Keine Daten verfügbar.",
        "api_error": "Abruf fehlgeschlagen: ",
        "historical_none": "Keine historischen Messwerte für diese Auswahl.",
        "api_base": "API-Basis-URL",
        "kiosk_on": "Anzeigemodus starten",
        "kiosk_off": "Anzeigemodus beenden",
        "lang": "Sprache",
        "time_window": "Zeitraum",
        "day": "Tag",
        "week": "Woche",
        "month": "Monat",
        "year": "Jahr",
        "slide": "Diashow (EN/DE im Wechsel)",
        "avg": "Durchschnitt",
    },
}

# ── Query/session state sync ──────────────────────────────────────────
def qp_get(name: str, default=None):
    return st.query_params.get(name, default)

def qp_get_bool(name: str, default: bool = False) -> bool:
    v = st.query_params.get(name)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "y")

def qp_set(**kwargs):
    changed = False
    for k, v in kwargs.items():
        if isinstance(v, bool):
            v = "1" if v else "0"
        else:
            v = str(v)
        if st.query_params.get(k) != v:
            st.query_params[k] = v
            changed = True
    # Prevent infinite rerun loop
    if changed and not st.session_state.get("_qp_initialized", False):
        st.session_state["_qp_initialized"] = True
        st.rerun()

if "lang" not in st.session_state:
    st.session_state.lang = qp_get("lang", "en")
if "slide_enabled" not in st.session_state:
    st.session_state.slide_enabled = qp_get_bool("slide", False)
if "kiosk" not in st.session_state:
    st.session_state.kiosk = qp_get_bool("kiosk", False)
if "slide_last_switch" not in st.session_state:
    st.session_state.slide_last_switch = time.time()

API_BASE = qp_get("api", DEFAULT_API_BASE)
T = TEXT[st.session_state.lang]

# ── CSS for ENERGY FLOW and header ────────────────────────────────────
st.markdown(dedent("""
<style>
.section-title{
  font-weight:700; font-size:clamp(28px,3.2vw,44px);
  line-height:1.1; margin: 0 0 6px 0;
}
.flow-band{ background:#025b9c; border-radius:12px; padding:14px 16px; margin:8px 0 12px; position:relative;}
.flow-grid{display:grid;align-items:center;grid-template-columns:180px 1fr 180px 1fr 180px;column-gap:36px;width:min(1200px,95%);}
.flow-node{text-align:center;color:#fff;}
.flow-node img{max-height:52px;border-radius:8px;}
.flow-node .cap{font-size:13px;margin-top:8px;color:#e7f0f7;}
.flow-line{position:relative;height:3px;background:transparent;overflow:hidden;}
.flow-line::before{content:"";position:absolute;left:-44px;right:-44px;top:-6px;bottom:-6px;background:radial-gradient(circle,rgba(255,255,255,1) 42%,rgba(255,255,255,0) 45%) 0 0/12px 12px repeat-x;animation:flow 1.1s linear infinite;opacity:.95;}
.flow-line.dc::before{filter:hue-rotate(90deg) saturate(140%);}
.flow-line.ac::before{filter:hue-rotate(200deg) saturate(140%);}
@keyframes flow{to{transform:translateX(44px);}}
</style>
"""), unsafe_allow_html=True)

if st.session_state.kiosk:
    st.markdown(dedent("""
    <style>
    [data-testid="stSidebar"] { display:none !important; }
    #MainMenu, footer { visibility:hidden; }
    .block-container { padding-top:.2rem; max-width:1920px; }
    </style>
    """), unsafe_allow_html=True)

# ── Sidebar / header controls ────────────────────────────────────────
def lang_radio(label="Language / Sprache", horizontal=False):
    choice = st.radio(label, ["English", "Deutsch"], horizontal=horizontal, key="lang_radio")
    st.session_state.lang = "en" if choice == "English" else "de"
    qp_set(lang=st.session_state.lang)

if not st.session_state.kiosk:
    with st.sidebar:
        st.markdown(f"**{T['controls']}**")
        lang_radio(horizontal=False)
        st.session_state.slide_enabled = st.checkbox(
            T["slide"], value=st.session_state.slide_enabled, key="slide_box"
        )
        qp_set(slide=st.session_state.slide_enabled)
        API_BASE = st.text_input(T["api_base"], value=API_BASE, key="api_base")
        st.button(T["kiosk_on"], on_click=lambda: qp_set(kiosk=True))
else:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"### ⚡ {TEXT[st.session_state.lang]['title']}")
    with c2:
        lang_radio(label=T["lang"], horizontal=True)
        st.button(T["kiosk_off"], on_click=lambda: qp_set(kiosk=False))

# Slideshow language flip
if st.session_state.slide_enabled:
    now = time.time()
    if now - st.session_state.slide_last_switch > 10:
        st.session_state.lang = "de" if st.session_state.lang == "en" else "en"
        st.session_state.slide_last_switch = now
        qp_set(lang=st.session_state.lang)
T = TEXT[st.session_state.lang]  # always refresh pointer

# ── API helpers ──────────────────────────────────────────────────────
@st.cache_data(ttl=15, show_spinner=False)
def _get(path, **params):
    # Ensure path starts with /
    path = "/" + path.lstrip("/")
    url = f"{API_BASE}{path}"  # Now: http://localhost:5000/api/reading/latest ✓
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_latest():
    try:
        return _get("api/readings/latest").get("reading", {})
    except Exception as e:
        st.warning(f"{T.get('api_error', 'API error')}: {e}")
        return {}

def fetch_history(start=None, end=None, limit=10000, order="asc"):
    try:
        params = {}
        if start: params["start"] = start
        if end:   params["end"]   = end
        params["limit"] = limit
        params["order"] = order
        data = _get("api/readings/history", **params)
        df = pd.DataFrame(data)
        if not df.empty:
            if "timestamp" not in df.columns and "ts" in df.columns:
                df["timestamp"] = pd.to_datetime(df["ts"], errors="coerce")
            else:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        return df
    except Exception as e:
        st.warning(f"{T.get('api_error', 'API error')}: {e}")
        return pd.DataFrame()

# ── Static asset utility ─────────────────────────────────────────────
def to_data_uri(path: str):
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None

# ── Header with big title & right-aligned logo ───────────────────────
left, right = st.columns([4, 2], vertical_alignment="center")
with left:
    st.markdown("""
    <style>
    @font-face {
      font-family: 'Calps Sans Semi Light';
      src: url('YOUR_CALPS_SANS_SEMI_LIGHT_WEBFONT_URL.woff2') format('woff2');
      font-weight: 400;
      font-style: normal;
    }
    .section-title {
      font-family: 'Calps Sans Semi Light', 'Helvetica Neue', Arial, sans-serif;
      font-weight: 400;
      font-size: clamp(28px,3.2vw,44px);
      line-height: 1.1;
      margin: 0 0 6px 0;
      color: #025b9c;
    }
    </style>
    <div class="section-title">THI Photovoltaics</div>
    """, unsafe_allow_html=True)
    st.caption(f'{T["last_updated"]} {datetime.utcnow():%Y-%m-%d %H:%M} UTC')
with right:
    st.markdown('<div style="text-align:right;">', unsafe_allow_html=True)
    st.image("dashboard/static/logo_text.jpg", use_container_width=False, width=220)
    st.markdown('</div>', unsafe_allow_html=True)

# ── Energy flow ──────────────────────────────────────────────────────
panel_svg = "https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/svg/1F5FB.svg"
inverter_svg = "https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/svg/1F50C.svg"
thi_logo_data = to_data_uri("dashboard/static/logo.png") or panel_svg

flow_html = f"""
<div class="flow-band">
  <div class="flow-grid">
    <div class="flow-node">
      <img src="{panel_svg}" alt="PV">
      <div class="cap">DC · PV</div>
    </div>
    <div class="flow-line dc"></div>
    <div class="flow-node">
      <img src="{inverter_svg}" alt="Inverter">
      <div class="cap">AC · Inverter</div>
    </div>
    <div class="flow-line ac"></div>
    <div class="flow-node">
      <img src="{thi_logo_data}" alt="THI">
      <div class="cap">THI</div>
    </div>
  </div>
</div>
"""
st.markdown(dedent(flow_html), unsafe_allow_html=True)

# ── Main layout ──────────────────────────────────────────────────────
left, right = st.columns([3, 1])

with right:
    st.markdown(f"**{T['lifetime_kpis']}**")
    latest = fetch_latest()
    df_latest = pd.DataFrame([latest]) if isinstance(latest, dict) else pd.DataFrame(latest)
    # Allow single reading (dict) or list
    if not df_latest.empty and "power" in df_latest:
        total_power = df_latest["power"].dropna().sum()
        avg_power = df_latest["power"].dropna().mean()
        st.metric(T["production"], f"{total_power:.1f} W")
        st.metric(T["avg"], f"{avg_power:.1f} W")
        st.metric(T["income"], "€123")
    else:
        st.info("No live KPIs")

with left:
    tab_viz, tab_dist = st.tabs([T["pv_generation"], "Power Distribution"])
    with tab_viz:
        time_window = st.radio(
            T["time_window"],
            [T["day"], T["week"], T["month"], T["year"]],
            horizontal=True,
        )

        now = datetime.utcnow()
        start = {
            T["day"]: now - timedelta(days=1),
            T["week"]: now - timedelta(days=7),
            T["month"]: now - timedelta(days=30),
            T["year"]: now - timedelta(days=365),
        }[time_window]

        df = fetch_history(start=start.isoformat(), limit=10000, order="asc")
        if not df.empty:
            df = df.sort_values("timestamp")
            if "power" not in df.columns or df["power"].isna().all():
                rng = np.random.default_rng(42)
                df["power"] = np.abs(rng.normal(100, 20, len(df)))

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["timestamp"], y=df["power"], mode="lines",
                name=T["pv_generation"], line=dict(color=GREEN, width=2)
            ))
            fig.update_yaxes(zeroline=True, zerolinewidth=1, zerolinecolor="#C9D5DC")
            fig.update_layout(
                margin=dict(l=10, r=10, t=8, b=10),
                height=320,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, x=0.02),
            )
            st.plotly_chart(fig, use_container_width=True)

            charge = 20 + 60 * np.clip(np.sin(np.linspace(-1.2, 1.2, len(df))), 0, None)
            peak_idx = int(np.argmax(charge))

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=df["timestamp"], y=charge, mode="lines",
                name=T["battery_charge"], line=dict(color=PURPLE, width=3)
            ))
            fig2.add_trace(go.Scatter(
                x=[df["timestamp"].iloc[peak_idx]], y=[charge[peak_idx]],
                mode="markers", marker=dict(size=10, color=PURPLE, line=dict(color="#fff", width=2)),
                showlegend=False
            ))
            fig2.update_layout(
                margin=dict(l=10, r=10, t=8, b=10),
                height=250,
                legend=dict(orientation="h", yanchor="bottom", y=-0.15, x=0.02),
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info(T["historical_none"])
    with tab_dist:
        st.info("Distribution view placeholder")
