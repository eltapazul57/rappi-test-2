"""
app.py — Dashboard de Inteligencia Competitiva para Rappi.

Ejecución:
    streamlit run app/app.py

Pestañas:
    1. Datos & Scraping — tabla de datos, botón de scraping real, filtros
    2. Hallazgos Competitivos — 5 hallazgos principales + 3 visualizaciones

Sin fallback: si no existe competitive_data.csv, se muestra estado vacío
con invitación a ejecutar el scraper.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.data import load_data
from app.components.sidebar import render_sidebar
from app.tabs.data_tab import render_tab_data
from app.tabs.insights_tab import render_tab_insights

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Inteligencia Competitiva — Rappi vs Uber Eats vs DiDi Food",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Panel de Inteligencia Competitiva")
    st.caption("Rappi vs Uber Eats vs DiDi Food — CDMX, México")

    df_raw = load_data()
    df_filtered, selected_product = render_sidebar(df_raw)

    tab1, tab2 = st.tabs(["Datos & Scraping", "Hallazgos Competitivos"])

    with tab1:
        render_tab_data(df_filtered)

    with tab2:
        render_tab_insights(df_filtered, selected_product)


if __name__ == "__main__":
    main()
