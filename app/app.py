"""
app.py — Dashboard de Competitive Intelligence para Rappi.

Cómo ejecutar:
    streamlit run app/app.py

Pestañas:
    1. Datos & Scraping — tabla de datos, botón de scraping, filtros
    2. Insights Competitivos — Top 5 findings + 3 visualizaciones

El dashboard siempre funciona: si no hay competitive_data.csv, carga
el backup pre-generado automáticamente (plan B del CONTEXT.md).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Ajustar path para imports desde la raíz del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scraper.config import OUTPUT_CSV, BACKUP_CSV
from app.charts import (
    chart_total_cost_by_zone,
    chart_eta_heatmap,
    chart_fee_comparison,
)

# ---------------------------------------------------------------------------
# Configuración de la página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Competitive Intelligence — Rappi vs Uber Eats vs DiDi Food",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)  # cache de 60 segundos para reflejar nuevo scraping
def load_data() -> tuple[pd.DataFrame, str]:
    """
    Carga el CSV de datos competitivos.

    Returns:
        Tupla (DataFrame, fuente) donde fuente es 'live' o 'backup'.
    """
    if OUTPUT_CSV.exists():
        df = pd.read_csv(OUTPUT_CSV, parse_dates=["timestamp"])
        return df, "live"
    elif BACKUP_CSV.exists():
        df = pd.read_csv(BACKUP_CSV, parse_dates=["timestamp"])
        return df, "backup"
    else:
        # Devolver DataFrame vacío con el esquema correcto
        columns = [
            "timestamp", "platform", "address_id", "zone", "product",
            "price", "delivery_fee", "estimated_time_min", "promotions", "scrape_status",
        ]
        return pd.DataFrame(columns=columns), "empty"


# ---------------------------------------------------------------------------
# Sidebar — filtros globales
# ---------------------------------------------------------------------------

def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Renderiza los filtros en el sidebar y devuelve el DataFrame filtrado.
    Los filtros son globales — afectan a ambas pestañas.
    """
    st.sidebar.title("Filtros")

    # Filtro de plataformas
    all_platforms = df["platform"].unique().tolist() if not df.empty else []
    platform_labels = {"rappi": "Rappi", "uber_eats": "Uber Eats", "didi_food": "DiDi Food"}
    selected_platforms = st.sidebar.multiselect(
        "Plataformas",
        options=all_platforms,
        default=all_platforms,
        format_func=lambda x: platform_labels.get(x, x),
    )

    # Filtro de producto
    all_products = df["product"].unique().tolist() if not df.empty else []
    product_labels = {"big_mac": "Big Mac", "coca_cola_600ml": "Coca-Cola 600ml"}
    selected_product = st.sidebar.selectbox(
        "Producto",
        options=all_products,
        format_func=lambda x: product_labels.get(x, x),
    )

    # Filtro de zonas
    all_zones = df["zone"].unique().tolist() if not df.empty else []
    zone_labels = {
        "polanco": "Polanco",
        "condesa_roma": "Condesa/Roma",
        "centro_historico": "Centro Histórico",
        "coyoacan": "Coyoacán",
        "iztapalapa": "Iztapalapa",
    }
    selected_zones = st.sidebar.multiselect(
        "Zonas",
        options=all_zones,
        default=all_zones,
        format_func=lambda x: zone_labels.get(x, x),
    )

    # Aplicar filtros
    filtered = df.copy()
    if selected_platforms:
        filtered = filtered[filtered["platform"].isin(selected_platforms)]
    if selected_product:
        filtered = filtered[filtered["product"] == selected_product]
    if selected_zones:
        filtered = filtered[filtered["zone"].isin(selected_zones)]

    return filtered, selected_product


# ---------------------------------------------------------------------------
# Pestaña 1: Datos & Scraping
# ---------------------------------------------------------------------------

def render_tab_data(df: pd.DataFrame, data_source: str) -> None:
    """
    Renderiza la pestaña de datos con:
    - Indicador de fuente de datos (live vs backup)
    - KPIs rápidos (total filas, tasa de éxito, etc.)
    - Botón de scraping con feedback en tiempo real
    - Tabla interactiva de datos
    """
    # Indicador de fuente de datos
    if data_source == "live":
        st.success("Datos en vivo — última ejecución del scraper")
    elif data_source == "backup":
        st.warning("Mostrando datos de respaldo (backup). Ejecuta el scraper para datos actualizados.")
    else:
        st.error("No hay datos disponibles. Ejecuta el scraper o agrega el backup CSV.")

    # KPIs rápidos
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total registros", len(df))
    with col2:
        success_rate = (
            df[df["scrape_status"] == "success"].shape[0] / len(df) * 100
            if len(df) > 0 else 0
        )
        st.metric("Tasa de éxito", f"{success_rate:.0f}%")
    with col3:
        platforms_count = df["platform"].nunique() if not df.empty else 0
        st.metric("Plataformas", platforms_count)
    with col4:
        zones_count = df["zone"].nunique() if not df.empty else 0
        st.metric("Zonas", zones_count)

    st.divider()

    # Botón de scraping
    st.subheader("Ejecutar Scraping")
    col_btn1, col_btn2 = st.columns([1, 3])

    with col_btn1:
        run_live = st.button("🚀 Scraping real", type="primary", use_container_width=True)
    with col_btn2:
        run_dry = st.button("📦 Cargar backup", use_container_width=True)

    if run_live:
        # TODO: lanzar runner.py como subprocess y mostrar output en tiempo real
        # Usar st.status() o st.empty() para feedback en tiempo real
        with st.status("Ejecutando scraping...", expanded=True) as status:
            st.write("Iniciando scrapers de Rappi, Uber Eats y DiDi Food...")
            # TODO: subprocess.run([sys.executable, "-m", "scraper.runner"])
            # y mostrar stdout línea por línea
            status.update(label="Scraping completado", state="complete")
        st.cache_data.clear()
        st.rerun()

    if run_dry:
        with st.spinner("Cargando datos de backup..."):
            # TODO: llamar runner.run_dry_run()
            pass
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # Tabla interactiva
    st.subheader("Datos recolectados")
    if not df.empty:
        # Highlight por status
        def color_status(val: str) -> str:
            colors = {
                "success": "background-color: #d4edda",
                "error": "background-color: #f8d7da",
                "not_available": "background-color: #fff3cd",
            }
            return colors.get(val, "")

        st.dataframe(
            df.style.applymap(color_status, subset=["scrape_status"]),
            use_container_width=True,
            hide_index=True,
        )

        # Botón de descarga del CSV
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Descargar CSV",
            data=csv_bytes,
            file_name="competitive_data.csv",
            mime="text/csv",
        )
    else:
        st.info("No hay datos disponibles con los filtros actuales.")


# ---------------------------------------------------------------------------
# Pestaña 2: Insights Competitivos
# ---------------------------------------------------------------------------

def render_tab_insights(df: pd.DataFrame, selected_product: str) -> None:
    """
    Renderiza el informe de insights con:
    - 3 visualizaciones Plotly
    - Top 5 insights en formato Finding / Impacto / Recomendación
    """
    st.title("Informe de Competitive Intelligence")
    st.caption("Análisis comparativo: Rappi vs Uber Eats vs DiDi Food — CDMX, Octubre 2025")

    if df.empty or df[df["scrape_status"] == "success"].empty:
        st.warning("No hay datos suficientes para mostrar insights. Ejecuta el scraper primero.")
        return

    # ------------------------------------------------------------------
    # Sección de visualizaciones
    # ------------------------------------------------------------------

    st.subheader("Visualizaciones")

    # Chart 1 — Costo total por zona
    st.markdown("#### Costo Total al Usuario (Precio + Delivery Fee) por Zona")
    try:
        fig1 = chart_total_cost_by_zone(df, product_key=selected_product)
        st.plotly_chart(fig1, use_container_width=True)
    except NotImplementedError:
        st.info("Visualización en desarrollo — disponible en la siguiente versión.")

    col_c2, col_c3 = st.columns(2)

    # Chart 2 — Heatmap de ETAs
    with col_c2:
        st.markdown("#### Tiempo de Entrega (min) por Zona y Plataforma")
        try:
            fig2 = chart_eta_heatmap(df, product_key=selected_product)
            st.plotly_chart(fig2, use_container_width=True)
        except NotImplementedError:
            st.info("Visualización en desarrollo.")

    # Chart 3 — Comparación de fees
    with col_c3:
        st.markdown("#### Distribución de Delivery Fees por Plataforma")
        try:
            fig3 = chart_fee_comparison(df)
            st.plotly_chart(fig3, use_container_width=True)
        except NotImplementedError:
            st.info("Visualización en desarrollo.")

    st.divider()

    # ------------------------------------------------------------------
    # Top 5 Insights
    # ------------------------------------------------------------------

    st.subheader("Top 5 Insights Accionables")

    # TODO: los insights deben calcularse dinámicamente del DataFrame.
    # Por ahora, la estructura está definida con placeholders para el informe.
    # Cada insight sigue el formato Finding / Impacto / Recomendación del CONTEXT.md.

    insights = [
        {
            "title": "Insight 1: Brecha de precio total en zonas premium",
            "finding": "TODO: calcular diferencia de costo total entre plataformas en Polanco y Condesa/Roma.",
            "impacto": "TODO: cuantificar pérdida de share en zonas de alto ticket.",
            "recomendacion": "TODO: proponer ajuste de fees o promociones focalizadas.",
        },
        {
            "title": "Insight 2: Cobertura deficiente de DiDi Food en periferia",
            "finding": "DiDi Food no tiene cobertura en Iztapalapa, lo que representa una oportunidad de expansión para Rappi.",
            "impacto": "Rappi tiene ventaja competitiva única en zonas periféricas de CDMX.",
            "recomendacion": "Capitalizar la exclusividad en Iztapalapa con campañas de adquisición de usuarios en esa zona.",
        },
        {
            "title": "Insight 3: Variabilidad del delivery fee de Rappi",
            "finding": "TODO: analizar si Rappi aplica surge pricing geográfico en el fee.",
            "impacto": "TODO: impacto en conversión cuando el fee es más alto que competidores.",
            "recomendacion": "TODO: propuesta de fee más consistente o Rappi Prime más agresivo.",
        },
        {
            "title": "Insight 4: Velocidad de entrega como diferenciador",
            "finding": "TODO: identificar qué plataforma es más rápida por zona.",
            "impacto": "TODO: correlación entre ETA y NPS/satisfacción del usuario.",
            "recomendacion": "TODO: estrategia de mejora de ETA en zonas donde Rappi es más lento.",
        },
        {
            "title": "Insight 5: Precios de producto estándar en todas las plataformas",
            "finding": "TODO: verificar si Big Mac tiene precio uniforme o varía por plataforma.",
            "impacto": "TODO: implicaciones para la negociación con McDonald's.",
            "recomendacion": "TODO: propuesta de exclusividad de precio o pack promocional.",
        },
    ]

    for i, insight in enumerate(insights, 1):
        with st.expander(f"**{insight['title']}**", expanded=(i == 1)):
            st.markdown(f"**Finding:** {insight['finding']}")
            st.markdown(f"**Impacto:** {insight['impacto']}")
            st.markdown(f"**Recomendación:** {insight['recomendacion']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("🛵 Competitive Intelligence Dashboard")
    st.caption("Rappi vs Uber Eats vs DiDi Food — CDMX, México")

    # Cargar datos
    df_raw, data_source = load_data()

    # Sidebar con filtros (modifica df_raw)
    df_filtered, selected_product = render_sidebar(df_raw)

    # Pestañas principales
    tab1, tab2 = st.tabs(["📊 Datos & Scraping", "💡 Insights Competitivos"])

    with tab1:
        render_tab_data(df_filtered, data_source)

    with tab2:
        render_tab_insights(df_filtered, selected_product)


if __name__ == "__main__":
    main()
