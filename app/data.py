import pandas as pd
import streamlit as st
from scraper.config import OUTPUT_CSV

CSV_COLUMNS = [
    "timestamp", "platform", "address_id", "zone", "product",
    "price", "delivery_fee", "estimated_time_min", "promotions", "scrape_status",
]

@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    """Carga el CSV de datos competitivos. Devuelve DataFrame vacío si no existe."""
    if OUTPUT_CSV.exists():
        return pd.read_csv(OUTPUT_CSV, parse_dates=["timestamp"])
    return pd.DataFrame(columns=CSV_COLUMNS)
