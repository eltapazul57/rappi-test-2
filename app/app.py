"""
app.py — Dashboard de Competitive Intelligence para Rappi.

Ejecución:
    streamlit run app/app.py

Pestañas:
    1. Datos & Scraping — tabla de datos, botón de scraping real, filtros
    2. Insights Competitivos — Top 5 findings + 3 visualizaciones

Sin fallback: si no existe competitive_data.csv, se muestra estado vacío
con invitación a ejecutar el scraper.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scraper.config import OUTPUT_CSV
from app.charts import (
    chart_total_cost_by_zone,
    chart_eta_heatmap,
    chart_fee_comparison,
)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Competitive Intelligence — Rappi vs Uber Eats vs DiDi Food",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSV_COLUMNS = [
    "timestamp", "platform", "address_id", "zone", "product",
    "price", "delivery_fee", "estimated_time_min", "promotions", "scrape_status",
]

PLATFORM_LABELS = {"rappi": "Rappi", "uber_eats": "Uber Eats", "didi_food": "DiDi Food"}
PRODUCT_LABELS = {"big_mac": "Big Mac", "coca_cola_600ml": "Coca-Cola 600ml"}
ZONE_LABELS = {
    "polanco": "Polanco",
    "condesa_roma": "Condesa/Roma",
    "centro_historico": "Centro Histórico",
    "coyoacan": "Coyoacán",
    "iztapalapa": "Iztapalapa",
}


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    """Carga el CSV de datos competitivos. Devuelve DataFrame vacío si no existe."""
    if OUTPUT_CSV.exists():
        return pd.read_csv(OUTPUT_CSV, parse_dates=["timestamp"])
    return pd.DataFrame(columns=CSV_COLUMNS)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Filtros globales. Devuelve (df_filtrado, producto_seleccionado)."""
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
        "Producto",
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
    if selected_product:
        filtered = filtered[filtered["product"] == selected_product]
    if selected_zones:
        filtered = filtered[filtered["zone"].isin(selected_zones)]

    return filtered, selected_product


# ---------------------------------------------------------------------------
# Pestaña 1: Datos & Scraping
# ---------------------------------------------------------------------------

def render_tab_data(df: pd.DataFrame) -> None:
    has_data = not df.empty

    if has_data:
        st.success(f"Datos cargados — {len(df)} registros de scraping real")
    else:
        st.warning(
            "No hay datos disponibles. Ejecuta el scraper con el botón de abajo "
            "o desde terminal: `python -m scraper.runner`"
        )

    # KPIs
    if has_data:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total registros", len(df))
        with col2:
            success_rate = (
                df[df["scrape_status"] == "success"].shape[0] / len(df) * 100
            )
            st.metric("Tasa de éxito", f"{success_rate:.0f}%")
        with col3:
            st.metric("Plataformas", df["platform"].nunique())
        with col4:
            st.metric("Zonas", df["zone"].nunique())

    st.divider()

    # Botón de scraping real
    st.subheader("Ejecutar Scraping")
    run_live = st.button("🚀 Ejecutar scraping real", type="primary")

    if run_live:
        _run_scraping_subprocess()

    st.divider()

    # Tabla de datos
    st.subheader("Datos recolectados")
    if has_data:
        def color_status(val: str) -> str:
            colors = {
                "success": "background-color: #d4edda",
                "error": "background-color: #f8d7da",
                "not_available": "background-color: #fff3cd",
            }
            return colors.get(val, "")

        st.dataframe(
            df.style.map(color_status, subset=["scrape_status"]),
            use_container_width=True,
            hide_index=True,
        )

        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Descargar CSV",
            data=csv_bytes,
            file_name="competitive_data.csv",
            mime="text/csv",
        )
    else:
        st.info("Sin datos. Ejecuta el scraper para generar competitive_data.csv.")


def _run_scraping_subprocess() -> None:
    """Ejecuta el runner como subprocess y muestra output en tiempo real."""
    with st.status("Ejecutando scraping...", expanded=True) as status:
        st.write("Lanzando scrapers de Rappi, Uber Eats y DiDi Food...")
        st.write("Esto puede tomar varios minutos por los delays de rate limiting.")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "scraper.runner"],
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutos máximo
            )

            if result.stdout:
                st.code(result.stdout[-3000:], language="text")  # últimas 3000 chars

            if result.returncode == 0:
                status.update(label="Scraping completado", state="complete")
            else:
                st.error(f"El scraper terminó con código {result.returncode}")
                if result.stderr:
                    st.code(result.stderr[-2000:], language="text")
                status.update(label="Scraping falló", state="error")

        except subprocess.TimeoutExpired:
            st.error("Timeout: el scraping excedió los 10 minutos.")
            status.update(label="Timeout", state="error")
        except Exception as exc:
            st.error(f"Error ejecutando scraper: {exc}")
            status.update(label="Error", state="error")

    st.cache_data.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Pestaña 2: Insights
# ---------------------------------------------------------------------------

def render_tab_insights(df: pd.DataFrame, selected_product: str) -> None:
    st.title("Informe de Competitive Intelligence")
    st.caption("Análisis comparativo: Rappi vs Uber Eats vs DiDi Food — CDMX")

    success_df = df[df["scrape_status"] == "success"] if not df.empty else df

    if success_df.empty:
        st.warning("No hay datos exitosos para mostrar insights. Ejecuta el scraper primero.")
        return

    # Visualizaciones
    st.subheader("Visualizaciones")

    st.markdown("#### Costo Total al Usuario (Precio + Delivery Fee) por Zona")
    try:
        fig1 = chart_total_cost_by_zone(df, product_key=selected_product)
        st.plotly_chart(fig1, use_container_width=True)
    except NotImplementedError:
        st.info("Visualización pendiente de implementación.")
    except Exception as exc:
        st.error(f"Error generando gráfica: {exc}")

    col_c2, col_c3 = st.columns(2)

    with col_c2:
        st.markdown("#### Tiempo de Entrega (min) por Zona y Plataforma")
        try:
            fig2 = chart_eta_heatmap(df, product_key=selected_product)
            st.plotly_chart(fig2, use_container_width=True)
        except NotImplementedError:
            st.info("Visualización pendiente de implementación.")
        except Exception as exc:
            st.error(f"Error: {exc}")

    with col_c3:
        st.markdown("#### Distribución de Delivery Fees por Plataforma")
        try:
            fig3 = chart_fee_comparison(df)
            st.plotly_chart(fig3, use_container_width=True)
        except NotImplementedError:
            st.info("Visualización pendiente de implementación.")
        except Exception as exc:
            st.error(f"Error: {exc}")

    st.divider()

    # Insights dinámicos
    st.subheader("Top 5 Insights Accionables")
    _render_dynamic_insights(success_df, selected_product)


def _render_dynamic_insights(df: pd.DataFrame, product_key: str) -> None:
    """Calcula y renderiza insights basados en los datos reales."""
    product_df = df[df["product"] == product_key] if product_key else df

    insights = []

    # Insight 1: Brecha de precio total por plataforma
    if not product_df.empty:
        product_df = product_df.copy()
        product_df["total_cost"] = product_df["price"].fillna(0) + product_df["delivery_fee"].fillna(0)
        avg_cost = product_df.groupby("platform")["total_cost"].mean()

        if len(avg_cost) >= 2:
            cheapest = avg_cost.idxmin()
            most_expensive = avg_cost.idxmax()
            diff = avg_cost[most_expensive] - avg_cost[cheapest]
            pct_diff = (diff / avg_cost[cheapest]) * 100 if avg_cost[cheapest] > 0 else 0

            insights.append({
                "title": "Insight 1: Brecha de costo total entre plataformas",
                "finding": (
                    f"{PLATFORM_LABELS.get(most_expensive, most_expensive)} es la plataforma más cara con un costo total "
                    f"promedio de ${avg_cost[most_expensive]:.0f} MXN, mientras que "
                    f"{PLATFORM_LABELS.get(cheapest, cheapest)} es la más barata con ${avg_cost[cheapest]:.0f} MXN "
                    f"(diferencia de ${diff:.0f}, {pct_diff:.0f}%)."
                ),
                "impacto": (
                    f"Los usuarios que comparan precios migrarán hacia {PLATFORM_LABELS.get(cheapest, cheapest)}. "
                    f"Una diferencia del {pct_diff:.0f}% en costo total puede impactar significativamente la conversión."
                ),
                "recomendacion": (
                    "Revisar la estructura de precios y fees para ser competitivo en costo total, "
                    "no solo en precio de producto."
                ),
            })

    # Insight 2: Cobertura geográfica
    zones_by_platform = df.groupby("platform")["zone"].nunique()
    total_zones = df["zone"].nunique()
    low_coverage = zones_by_platform[zones_by_platform < total_zones]

    if not low_coverage.empty:
        for plat, count in low_coverage.items():
            missing_zones = set(df["zone"].unique()) - set(df[df["platform"] == plat]["zone"].unique())
            if missing_zones:
                zone_names = ", ".join(ZONE_LABELS.get(z, z) for z in missing_zones)
                insights.append({
                    "title": f"Insight 2: Cobertura limitada de {PLATFORM_LABELS.get(plat, plat)}",
                    "finding": (
                        f"{PLATFORM_LABELS.get(plat, plat)} no tiene cobertura o disponibilidad en: {zone_names}. "
                        f"Cubre {count} de {total_zones} zonas."
                    ),
                    "impacto": (
                        "Las zonas sin cobertura de un competidor son oportunidades de exclusividad "
                        "para las plataformas que sí operan ahí."
                    ),
                    "recomendacion": (
                        f"Capitalizar la ausencia de {PLATFORM_LABELS.get(plat, plat)} en esas zonas "
                        "con campañas de adquisición de usuarios y promociones exclusivas."
                    ),
                })
                break  # solo un insight de cobertura

    # Insight 3: Variabilidad del fee
    if "delivery_fee" in df.columns:
        fee_stats = df.groupby("platform")["delivery_fee"].agg(["mean", "std", "min", "max"])
        fee_stats = fee_stats.dropna()

        if not fee_stats.empty:
            most_variable = fee_stats["std"].idxmax() if fee_stats["std"].max() > 0 else None
            if most_variable:
                stats = fee_stats.loc[most_variable]
                insights.append({
                    "title": "Insight 3: Variabilidad geográfica del delivery fee",
                    "finding": (
                        f"{PLATFORM_LABELS.get(most_variable, most_variable)} tiene el fee de envío más variable: "
                        f"de ${stats['min']:.0f} a ${stats['max']:.0f} MXN (promedio ${stats['mean']:.0f}, "
                        f"desviación ${stats['std']:.0f})."
                    ),
                    "impacto": (
                        "Un fee variable sugiere surge pricing geográfico. Usuarios en zonas caras "
                        "pueden percibir la plataforma como inconsistente."
                    ),
                    "recomendacion": (
                        "Evaluar si un fee más uniforme (o un programa de envío gratis tipo Prime) "
                        "mejora la retención en zonas periféricas."
                    ),
                })

    # Insight 4: Velocidad de entrega
    if "estimated_time_min" in df.columns:
        eta_avg = df.groupby("platform")["estimated_time_min"].mean().dropna()

        if len(eta_avg) >= 2:
            fastest = eta_avg.idxmin()
            slowest = eta_avg.idxmax()
            insights.append({
                "title": "Insight 4: Velocidad de entrega como diferenciador",
                "finding": (
                    f"{PLATFORM_LABELS.get(fastest, fastest)} es la plataforma más rápida con un ETA promedio "
                    f"de {eta_avg[fastest]:.0f} min, vs {PLATFORM_LABELS.get(slowest, slowest)} con {eta_avg[slowest]:.0f} min."
                ),
                "impacto": (
                    f"Una diferencia de {eta_avg[slowest] - eta_avg[fastest]:.0f} min en ETA puede ser decisiva "
                    "para usuarios que priorizan velocidad sobre precio."
                ),
                "recomendacion": (
                    "Si Rappi no es el más rápido, invertir en optimización logística en las zonas "
                    "donde el gap de ETA es mayor."
                ),
            })

    # Insight 5: Precios de producto entre plataformas
    if not product_df.empty:
        price_by_platform = product_df.groupby("platform")["price"].mean().dropna()

        if len(price_by_platform) >= 2:
            price_range = price_by_platform.max() - price_by_platform.min()
            pct_range = (price_range / price_by_platform.min()) * 100 if price_by_platform.min() > 0 else 0

            product_name = PRODUCT_LABELS.get(product_key, product_key)
            insights.append({
                "title": f"Insight 5: Variación de precio del {product_name} entre plataformas",
                "finding": (
                    f"El precio del {product_name} varía ${price_range:.0f} MXN entre plataformas "
                    f"({pct_range:.0f}% de diferencia). Rango: ${price_by_platform.min():.0f} - ${price_by_platform.max():.0f}."
                ),
                "impacto": (
                    "Un producto estandarizado no debería tener diferencias significativas de precio. "
                    "Esto sugiere diferentes acuerdos comerciales con el proveedor."
                ),
                "recomendacion": (
                    "Negociar con el proveedor para igualar o mejorar el precio de la competencia. "
                    "Ofrecer packs o combos exclusivos como alternativa."
                ),
            })

    # Fallback si no se pudo calcular ningún insight
    if not insights:
        st.info("No hay suficientes datos para generar insights. Necesitas al menos 2 plataformas con datos exitosos.")
        return

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

    df_raw = load_data()
    df_filtered, selected_product = render_sidebar(df_raw)

    tab1, tab2 = st.tabs(["📊 Datos & Scraping", "💡 Insights Competitivos"])

    with tab1:
        render_tab_data(df_filtered)

    with tab2:
        render_tab_insights(df_filtered, selected_product)


if __name__ == "__main__":
    main()
