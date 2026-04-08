import pandas as pd
import streamlit as st

from app.charts import PLATFORM_LABELS, PRODUCT_LABELS, ZONE_LABELS

def render_sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Filtros globales. Devuelve (df_filtrado, producto_seleccionado).

    El filtro de producto NO se aplica al DataFrame: se pasa como seleccion
    aparte para que los charts por producto lo usen, mientras que los charts
    cross-producto (fee comparison, data quality) ven todos los productos.
    """
    st.sidebar.title("Filtros")

    if df.empty:
        return df, ""

    all_platforms = df["platform"].unique().tolist()
    selected_platforms = st.sidebar.multiselect(
        "Plataformas",
        options=all_platforms,
        default=all_platforms,
        format_func=lambda x: PLATFORM_LABELS.get(x, x),
    )

    all_products = df["product"].unique().tolist()
    selected_product = st.sidebar.selectbox(
        "Producto (para graficas por producto)",
        options=all_products,
        format_func=lambda x: PRODUCT_LABELS.get(x, x),
    )

    all_zones = df["zone"].unique().tolist()
    selected_zones = st.sidebar.multiselect(
        "Zonas",
        options=all_zones,
        default=all_zones,
        format_func=lambda x: ZONE_LABELS.get(x, x),
    )

    filtered = df.copy()
    if selected_platforms:
        filtered = filtered[filtered["platform"].isin(selected_platforms)]
    if selected_zones:
        filtered = filtered[filtered["zone"].isin(selected_zones)]

    return filtered, selected_product
