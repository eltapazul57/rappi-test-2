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
from app.ai_insights import generate_insights_with_ai, is_ai_ready
from app.charts import (
    chart_total_cost_by_zone,
    chart_eta_heatmap,
    chart_fee_comparison,
    chart_price_breakdown,
    chart_data_quality,
)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Competitive Intelligence — Rappi vs Uber Eats vs DiDi Food",
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

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        run_both = st.button("Ejecutar scraping (Rappi + Uber Eats)", type="primary")
    with col_btn2:
        run_rappi = st.button("Solo Rappi")
        run_uber = st.button("Solo Uber Eats")

    if run_both:
        _run_scraping_subprocess()
    elif run_rappi:
        _run_scraping_subprocess(platforms=["rappi"])
    elif run_uber:
        _run_scraping_subprocess(platforms=["uber_eats"])

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


def _run_scraping_subprocess(platforms: list[str] | None = None) -> None:
    """Ejecuta el runner como subprocess con streaming de logs en tiempo real."""
    cmd = [sys.executable, "-m", "scraper.runner"]
    if platforms:
        cmd += ["--platforms"] + platforms

    platform_label = ", ".join(platforms) if platforms else "Rappi + Uber Eats"
    st.info(f"Iniciando scraping de: {platform_label}. No cierres esta ventana.")

    log_area = st.empty()
    log_lines: list[str] = []
    status_placeholder = st.empty()

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # mezcla stderr + stdout en un solo stream
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if line:
                log_lines.append(line)
                # Mostramos las últimas 60 líneas para no sobrecargar la UI
                log_area.code("\n".join(log_lines[-60:]), language="text")

        proc.wait()

        if proc.returncode == 0:
            status_placeholder.success("Scraping completado correctamente. El CSV ha sido actualizado.")
        else:
            status_placeholder.error(f"El scraper terminó con código de error {proc.returncode}. Revisa los logs de arriba.")

    except Exception as exc:
        status_placeholder.error(f"Error iniciando el scraper: {exc}")

    st.cache_data.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Pestaña 2: Insights
# ---------------------------------------------------------------------------

def render_tab_insights(df: pd.DataFrame, selected_product: str) -> None:
    st.title("Informe de Competitive Intelligence")
    st.caption("Análisis comparativo: Rappi vs Uber Eats vs DiDi Food — CDMX, México")

    success_df = df[df["scrape_status"] == "success"].copy() if not df.empty else df

    if success_df.empty:
        st.warning("No hay datos exitosos para mostrar insights. Ejecuta el scraper primero.")
        return

    # ── Executive Summary ─────────────────────────────────────────────
    _render_executive_summary(success_df, selected_product)

    st.divider()

    # ── Visualizaciones ───────────────────────────────────────────────
    st.header("Visualizaciones Comparativas")

    # Chart 1: Total cost by zone (full width)
    st.markdown("#### 1. Costo Total al Usuario (Precio + Delivery Fee) por Zona")
    try:
        fig1 = chart_total_cost_by_zone(df, product_key=selected_product)
        st.plotly_chart(fig1, use_container_width=True)
    except Exception as exc:
        st.error(f"Error generando gráfica: {exc}")

    # Charts 2 & 3 side by side
    col_c2, col_c3 = st.columns(2)

    with col_c2:
        st.markdown("#### 2. Tiempo de Entrega por Zona y Plataforma")
        try:
            fig2 = chart_eta_heatmap(df, product_key=selected_product)
            st.plotly_chart(fig2, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    with col_c3:
        st.markdown("#### 3. Distribución de Delivery Fees")
        try:
            fig3 = chart_fee_comparison(df)
            st.plotly_chart(fig3, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    # Chart 4: Price breakdown (full width)
    st.markdown("#### 4. Desglose de Costo: Precio del Producto vs Delivery Fee")
    try:
        fig4 = chart_price_breakdown(df, product_key=selected_product)
        st.plotly_chart(fig4, use_container_width=True)
    except Exception as exc:
        st.error(f"Error: {exc}")

    st.divider()

    # ── Top 5 Insights (Inteligencia Artificial) ──────────────────────
    st.header("Top 5 Insights (Inteligencia Artificial)")
    st.markdown("Genera un análisis estratégico profundo y dinámico alimentando un modelo LLM con los datos reales capturados.")

    if is_ai_ready():
        if st.button("Generar Insights Estratégicos con OpenAI", type="primary"):
            with st.spinner("Analizando precios, tiempos de entrega y promociones cruzadas..."):
                ai_markdown = generate_insights_with_ai(success_df)
                st.markdown(ai_markdown)
    else:
        st.warning("OpenAI no está configurado. Para activar la Inteligencia Artificial, instala `requirements.txt` y renombra tu `.env.example` a `.env` incluyendo un `OPENAI_API_KEY` válido.")

    st.divider()

    # ── Insights Básicos (Locales) ────────────────────────────────────
    st.header("Insights Básicos (Algorítmicos)")
    st.markdown("_Insights heurísticos calculados estáticamente (Fallback)._")
    with st.expander("Ver Análisis Estático", expanded=False):
        _render_dynamic_insights(success_df, selected_product)

    st.divider()

    # ── Promotions analysis ───────────────────────────────────────────
    _render_promotions_analysis(success_df)

    st.divider()

    # ── Methodology ───────────────────────────────────────────────────
    _render_methodology(df)


# ---------------------------------------------------------------------------
# Executive Summary
# ---------------------------------------------------------------------------

def _render_executive_summary(df: pd.DataFrame, product_key: str) -> None:
    """KPI cards + one-paragraph summary at the top of the insights tab."""
    st.header("Resumen Ejecutivo")

    platforms = df["platform"].unique()
    zones = df["zone"].unique()
    n_success = len(df)
    total_rows_all = n_success  # already filtered to success

    # Compute key metrics
    df = df.copy()
    df["total_cost"] = df["price"].fillna(0) + df["delivery_fee"].fillna(0)

    avg_price = df["price"].mean()
    avg_fee = df["delivery_fee"].mean()
    avg_eta = df["estimated_time_min"].mean()
    avg_total = df["total_cost"].mean()

    # KPI row
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric("Plataformas", len(platforms))
    with k2:
        st.metric("Zonas CDMX", len(zones))
    with k3:
        st.metric("Registros exitosos", n_success)
    with k4:
        st.metric("Precio promedio", f"${avg_price:.0f}" if pd.notna(avg_price) else "N/D")
    with k5:
        st.metric("ETA promedio", f"{avg_eta:.0f} min" if pd.notna(avg_eta) else "N/D")

    # Narrative summary
    platform_names = ", ".join(PLATFORM_LABELS.get(p, p) for p in sorted(platforms))
    zone_names = ", ".join(ZONE_LABELS.get(z, z) for z in sorted(zones))
    product_name = PRODUCT_LABELS.get(product_key, product_key)

    # Cheapest platform for selected product
    product_df = df[df["product"] == product_key] if product_key else df
    summary_parts = []

    if not product_df.empty:
        cost_by_plat = product_df.groupby("platform")["total_cost"].mean()
        if len(cost_by_plat) >= 2:
            cheapest = cost_by_plat.idxmin()
            most_exp = cost_by_plat.idxmax()
            diff_pct = ((cost_by_plat[most_exp] - cost_by_plat[cheapest]) / cost_by_plat[cheapest] * 100)
            summary_parts.append(
                f"Para **{product_name}**, **{PLATFORM_LABELS.get(cheapest, cheapest)}** ofrece el costo total más bajo "
                f"(${cost_by_plat[cheapest]:.0f} MXN promedio), mientras que "
                f"**{PLATFORM_LABELS.get(most_exp, most_exp)}** es {diff_pct:.0f}% más cara."
            )
        elif len(cost_by_plat) == 1:
            plat = cost_by_plat.index[0]
            summary_parts.append(
                f"Para **{product_name}**, solo se tienen datos de **{PLATFORM_LABELS.get(plat, plat)}** "
                f"con un costo total promedio de ${cost_by_plat.iloc[0]:.0f} MXN."
            )

    # ETA insight
    eta_by_plat = df.groupby("platform")["estimated_time_min"].mean().dropna()
    if len(eta_by_plat) >= 2:
        fastest = eta_by_plat.idxmin()
        summary_parts.append(
            f"En velocidad de entrega, **{PLATFORM_LABELS.get(fastest, fastest)}** lidera con "
            f"un ETA promedio de {eta_by_plat[fastest]:.0f} min."
        )
    elif len(eta_by_plat) == 1:
        plat = eta_by_plat.index[0]
        summary_parts.append(
            f"El ETA promedio de **{PLATFORM_LABELS.get(plat, plat)}** es de {eta_by_plat.iloc[0]:.0f} min."
        )

    # Fee coverage
    fee_filled = df["delivery_fee"].notna().sum()
    fee_pct = fee_filled / len(df) * 100 if len(df) > 0 else 0
    if fee_pct < 100:
        summary_parts.append(
            f"El delivery fee fue capturado en {fee_pct:.0f}% de los registros — "
            f"las zonas sin dato pueden indicar envío gratis o limitaciones del scraper."
        )

    st.markdown(
        f"Este informe analiza datos de **{platform_names}** en **{len(zones)} zonas de CDMX** "
        f"({zone_names}). "
        + " ".join(summary_parts)
    )


# ---------------------------------------------------------------------------
# Dynamic Insights (Top 5)
# ---------------------------------------------------------------------------

def _render_dynamic_insights(df: pd.DataFrame, product_key: str) -> None:
    """Calcula y renderiza insights basados en los datos reales."""
    product_df = df[df["product"] == product_key].copy() if product_key else df.copy()

    insights: list[dict] = []

    # ── Insight 1: Brecha de costo total ──────────────────────────────
    if not product_df.empty:
        product_df["total_cost"] = product_df["price"].fillna(0) + product_df["delivery_fee"].fillna(0)
        avg_cost = product_df.groupby("platform")["total_cost"].mean()

        if len(avg_cost) >= 2:
            cheapest = avg_cost.idxmin()
            most_expensive = avg_cost.idxmax()
            diff = avg_cost[most_expensive] - avg_cost[cheapest]
            pct_diff = (diff / avg_cost[cheapest]) * 100 if avg_cost[cheapest] > 0 else 0

            insights.append({
                "title": "Brecha de costo total entre plataformas",
                "finding": (
                    f"{PLATFORM_LABELS.get(most_expensive, most_expensive)} es la plataforma más cara con un costo total "
                    f"promedio de ${avg_cost[most_expensive]:.0f} MXN, mientras que "
                    f"{PLATFORM_LABELS.get(cheapest, cheapest)} es la más barata con ${avg_cost[cheapest]:.0f} MXN "
                    f"(diferencia de ${diff:.0f}, {pct_diff:.0f}%)."
                ),
                "impacto": (
                    f"Los usuarios price-sensitive migrarán hacia {PLATFORM_LABELS.get(cheapest, cheapest)}. "
                    f"Una diferencia del {pct_diff:.0f}% en costo total impacta directamente la tasa de conversión "
                    f"y el market share en zonas competidas."
                ),
                "recomendacion": (
                    "Revisar la estructura de precios y fees para ser competitivo en **costo total al usuario**, "
                    "no solo en precio de producto. Considerar absorber parcialmente el fee en zonas de alta competencia."
                ),
            })
        elif len(avg_cost) == 1:
            plat = avg_cost.index[0]
            product_name = PRODUCT_LABELS.get(product_key, product_key)

            # Intra-platform variability
            zone_cost = product_df.groupby("zone")["total_cost"].mean()
            if zone_cost.max() - zone_cost.min() > 5:
                cheapest_zone = ZONE_LABELS.get(zone_cost.idxmin(), zone_cost.idxmin())
                expensive_zone = ZONE_LABELS.get(zone_cost.idxmax(), zone_cost.idxmax())
                insights.append({
                    "title": f"Variabilidad de costo de {product_name} por zona",
                    "finding": (
                        f"El costo total del {product_name} en {PLATFORM_LABELS.get(plat, plat)} varía "
                        f"de ${zone_cost.min():.0f} a ${zone_cost.max():.0f} MXN entre zonas. "
                        f"La zona más barata es {cheapest_zone} y la más cara {expensive_zone}."
                    ),
                    "impacto": (
                        f"Una diferencia de ${zone_cost.max() - zone_cost.min():.0f} MXN en el mismo producto "
                        "entre zonas de la misma ciudad indica pricing geográfico o diferencias de oferta. "
                        "Usuarios que comparan sentirán inconsistencia."
                    ),
                    "recomendacion": (
                        "Investigar la causa de la variación (surge, tiendas distintas, restaurantes con precios diferentes) "
                        "y evaluar estandarización de precios para productos de referencia."
                    ),
                })

    # ── Insight 2: Cobertura geográfica ───────────────────────────────
    zones_by_platform = df.groupby("platform")["zone"].nunique()
    total_zones = df["zone"].nunique()
    low_coverage = zones_by_platform[zones_by_platform < total_zones]

    if not low_coverage.empty:
        for plat, count in low_coverage.items():
            missing_zones = set(df["zone"].unique()) - set(df[df["platform"] == plat]["zone"].unique())
            if missing_zones:
                zone_names = ", ".join(ZONE_LABELS.get(z, z) for z in missing_zones)
                insights.append({
                    "title": f"Cobertura limitada de {PLATFORM_LABELS.get(plat, plat)}",
                    "finding": (
                        f"{PLATFORM_LABELS.get(plat, plat)} no tiene cobertura o disponibilidad en: {zone_names}. "
                        f"Cubre solo {count} de {total_zones} zonas evaluadas."
                    ),
                    "impacto": (
                        "Las zonas sin cobertura de un competidor representan oportunidades de exclusividad "
                        "y menor presión de precios para las plataformas que sí operan ahí."
                    ),
                    "recomendacion": (
                        f"Capitalizar la ausencia de {PLATFORM_LABELS.get(plat, plat)} en esas zonas "
                        "con campañas de adquisición de usuarios y partnerships exclusivos con restaurantes locales."
                    ),
                })
                break
    else:
        # All platforms cover all zones — note parity
        if len(zones_by_platform) >= 2:
            insights.append({
                "title": "Paridad en cobertura geográfica",
                "finding": (
                    f"Todas las plataformas ({', '.join(PLATFORM_LABELS.get(p, p) for p in zones_by_platform.index)}) "
                    f"tienen presencia en las {total_zones} zonas evaluadas de CDMX."
                ),
                "impacto": (
                    "No hay ventaja geográfica inherente. La diferenciación debe venir de precio, "
                    "velocidad, promociones, o calidad de servicio."
                ),
                "recomendacion": (
                    "Enfocarse en diferenciadores no geográficos: tiempos de entrega, fees competitivos, "
                    "y programas de lealtad para retener usuarios en zonas con alta competencia."
                ),
            })

    # ── Insight 3: Variabilidad del delivery fee ──────────────────────
    fee_data = df.dropna(subset=["delivery_fee"])
    if not fee_data.empty:
        fee_stats = fee_data.groupby("platform")["delivery_fee"].agg(["mean", "std", "min", "max", "count"])

        if len(fee_stats) >= 2:
            most_variable = fee_stats["std"].idxmax() if fee_stats["std"].max() > 0 else None
            if most_variable:
                stats = fee_stats.loc[most_variable]
                insights.append({
                    "title": "Variabilidad geográfica del delivery fee",
                    "finding": (
                        f"{PLATFORM_LABELS.get(most_variable, most_variable)} tiene el fee de envío más variable: "
                        f"de ${stats['min']:.0f} a ${stats['max']:.0f} MXN (promedio ${stats['mean']:.0f}, "
                        f"desviación ${stats['std']:.1f})."
                    ),
                    "impacto": (
                        "Alta variabilidad en fees genera percepción de inconsistencia. "
                        "Usuarios en zonas con fees altos pueden sentirse penalizados y buscar alternativas."
                    ),
                    "recomendacion": (
                        "Evaluar si un fee más uniforme o un programa de envío gratis (tipo Rappi Prime) "
                        "mejora la retención en zonas periféricas de mayor costo logístico."
                    ),
                })
        elif len(fee_stats) == 1:
            plat = fee_stats.index[0]
            stats = fee_stats.iloc[0]
            free_count = (fee_data[fee_data["platform"] == plat]["delivery_fee"] == 0).sum()
            free_pct = free_count / stats["count"] * 100 if stats["count"] > 0 else 0
            insights.append({
                "title": f"Patrón de delivery fee en {PLATFORM_LABELS.get(plat, plat)}",
                "finding": (
                    f"El delivery fee de {PLATFORM_LABELS.get(plat, plat)} promedia ${stats['mean']:.0f} MXN "
                    f"(rango: ${stats['min']:.0f}–${stats['max']:.0f}). "
                    f"El {free_pct:.0f}% de los scrapes muestra envío gratis."
                ),
                "impacto": (
                    "Un fee de $0 frecuente sugiere promociones agresivas de envío gratis o umbral mínimo de compra. "
                    "Esto puede ser insostenible a largo plazo pero aumenta volumen a corto."
                ),
                "recomendacion": (
                    "Analizar si el envío gratis está asociado a restaurantes específicos (subsidiado por el merchant) "
                    "o a una promoción de plataforma, para decidir si igualar o diferenciar en otro eje."
                ),
            })

    # ── Insight 4: Velocidad de entrega ───────────────────────────────
    eta_data = df.dropna(subset=["estimated_time_min"])
    if not eta_data.empty:
        eta_avg = eta_data.groupby("platform")["estimated_time_min"].mean()

        if len(eta_avg) >= 2:
            fastest = eta_avg.idxmin()
            slowest = eta_avg.idxmax()
            gap = eta_avg[slowest] - eta_avg[fastest]
            insights.append({
                "title": "Velocidad de entrega como diferenciador",
                "finding": (
                    f"{PLATFORM_LABELS.get(fastest, fastest)} es la plataforma más rápida con un ETA promedio "
                    f"de {eta_avg[fastest]:.0f} min, vs {PLATFORM_LABELS.get(slowest, slowest)} con {eta_avg[slowest]:.0f} min "
                    f"(gap de {gap:.0f} min)."
                ),
                "impacto": (
                    f"Una diferencia de {gap:.0f} min en ETA puede ser decisiva para usuarios que priorizan velocidad. "
                    "Estudios de mercado muestran que cada minuto extra reduce la probabilidad de recompra."
                ),
                "recomendacion": (
                    "Si Rappi no es el más rápido, invertir en optimización logística (dark stores, micro-fulfillment) "
                    "en las zonas donde el gap de ETA es mayor. Comunicar velocidad como diferenciador en marketing."
                ),
            })
        elif len(eta_avg) == 1:
            plat = eta_avg.index[0]
            eta_by_zone = eta_data[eta_data["platform"] == plat].groupby("zone")["estimated_time_min"].mean()
            if not eta_by_zone.empty:
                slowest_zone = ZONE_LABELS.get(eta_by_zone.idxmax(), eta_by_zone.idxmax())
                fastest_zone = ZONE_LABELS.get(eta_by_zone.idxmin(), eta_by_zone.idxmin())
                insights.append({
                    "title": f"Variación de ETA por zona en {PLATFORM_LABELS.get(plat, plat)}",
                    "finding": (
                        f"El ETA de {PLATFORM_LABELS.get(plat, plat)} varía de {eta_by_zone.min():.0f} min "
                        f"({fastest_zone}) a {eta_by_zone.max():.0f} min ({slowest_zone}). "
                        f"Promedio general: {eta_avg.iloc[0]:.0f} min."
                    ),
                    "impacto": (
                        f"Zonas periféricas como {slowest_zone} muestran ETAs significativamente mayores, "
                        "lo que correlaciona con menor frecuencia de uso y menor retención."
                    ),
                    "recomendacion": (
                        f"Evaluar la viabilidad de micro dark stores o partnerships con tiendas locales "
                        f"en {slowest_zone} para reducir el ETA y aumentar penetración."
                    ),
                })

    # ── Insight 5: Precio del producto ────────────────────────────────
    if not product_df.empty:
        price_by_platform = product_df.groupby("platform")["price"].mean().dropna()
        product_name = PRODUCT_LABELS.get(product_key, product_key)

        if len(price_by_platform) >= 2:
            price_range = price_by_platform.max() - price_by_platform.min()
            pct_range = (price_range / price_by_platform.min()) * 100 if price_by_platform.min() > 0 else 0

            insights.append({
                "title": f"Variación de precio del {product_name} entre plataformas",
                "finding": (
                    f"El precio del {product_name} varía ${price_range:.0f} MXN entre plataformas "
                    f"({pct_range:.0f}% de diferencia). "
                    f"Rango: ${price_by_platform.min():.0f} – ${price_by_platform.max():.0f}."
                ),
                "impacto": (
                    "Un producto estandarizado no debería tener diferencias significativas de precio. "
                    "Esto sugiere diferentes comisiones de plataforma o acuerdos comerciales con el merchant."
                ),
                "recomendacion": (
                    "Negociar con el proveedor para igualar o mejorar el precio de la competencia. "
                    "Considerar ofrecer combos exclusivos como alternativa de precio percibido."
                ),
            })
        elif len(price_by_platform) == 1:
            plat = price_by_platform.index[0]
            price_by_zone = product_df[product_df["platform"] == plat].groupby("zone")["price"].mean()
            if price_by_zone.max() - price_by_zone.min() > 5:
                insights.append({
                    "title": f"Dispersión de precio del {product_name} por zona",
                    "finding": (
                        f"En {PLATFORM_LABELS.get(plat, plat)}, el {product_name} varía de "
                        f"${price_by_zone.min():.0f} a ${price_by_zone.max():.0f} MXN entre zonas. "
                        f"Las zonas más baratas: {', '.join(ZONE_LABELS.get(z, z) for z in price_by_zone.nsmallest(2).index)}."
                    ),
                    "impacto": (
                        f"Una variación de ${price_by_zone.max() - price_by_zone.min():.0f} MXN en el mismo producto "
                        "indica que diferentes restaurantes/tiendas están sirviendo el producto con precios distintos."
                    ),
                    "recomendacion": (
                        "Verificar si la variación proviene de distintas sucursales con pricing independiente. "
                        "Estandarizar precios en productos de referencia mejora la percepción de confianza."
                    ),
                })

    # ── Render ────────────────────────────────────────────────────────
    if not insights:
        st.info(
            "No hay suficientes datos para generar insights automáticos. "
            "Ejecuta el scraper para al menos 1 plataforma con datos exitosos."
        )
        return

    for i, insight in enumerate(insights):
        with st.expander(f"**Insight {i + 1}: {insight['title']}**", expanded=(i < 2)):
            st.markdown(f"**Finding:** {insight['finding']}")
            st.markdown(f"**Impacto:** {insight['impacto']}")
            st.markdown(f"**Recomendacion:** {insight['recomendacion']}")


# ---------------------------------------------------------------------------
# Promotions Analysis
# ---------------------------------------------------------------------------

def _render_promotions_analysis(df: pd.DataFrame) -> None:
    """Section dedicated to promotions found during scraping."""
    st.header("Análisis de Promociones")

    has_promos = df["promotions"].notna() & (df["promotions"].astype(str).str.strip() != "")
    promo_df = df[has_promos]

    if promo_df.empty:
        st.info(
            "No se detectaron promociones activas en este scrape. "
            "Esto puede deberse a:\n"
            "- Las plataformas no mostraban promociones al momento del scrape\n"
            "- Las promociones requieren login o historial de usuario para mostrarse\n"
            "- Los selectores de extracción no capturaron banners promocionales"
        )

        # Still show what percentage have promos
        total = len(df)
        st.metric("Registros con promoción detectada", f"0 de {total} (0%)")
        return

    total = len(df)
    promo_count = len(promo_df)
    promo_pct = promo_count / total * 100 if total > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Registros con promoción", f"{promo_count} de {total} ({promo_pct:.0f}%)")
    with col2:
        platforms_with_promos = promo_df["platform"].nunique()
        st.metric("Plataformas con promos", platforms_with_promos)
    with col3:
        zones_with_promos = promo_df["zone"].nunique()
        st.metric("Zonas con promos", zones_with_promos)

    # Table of promotions found
    st.markdown("#### Promociones detectadas")
    promo_display = promo_df[["platform", "zone", "product", "promotions"]].copy()
    promo_display["platform"] = promo_display["platform"].map(PLATFORM_LABELS).fillna(promo_display["platform"])
    promo_display["zone"] = promo_display["zone"].map(ZONE_LABELS).fillna(promo_display["zone"])
    promo_display["product"] = promo_display["product"].map(PRODUCT_LABELS).fillna(promo_display["product"])
    promo_display.columns = ["Plataforma", "Zona", "Producto", "Promoción"]
    st.dataframe(promo_display, use_container_width=True, hide_index=True)

    # Promo coverage by platform
    if len(df["platform"].unique()) > 1:
        st.markdown("#### Cobertura promocional por plataforma")
        promo_by_plat = []
        for plat in df["platform"].unique():
            plat_df = df[df["platform"] == plat]
            plat_promos = plat_df[
                plat_df["promotions"].notna() & (plat_df["promotions"].astype(str).str.strip() != "")
            ]
            promo_by_plat.append({
                "Plataforma": PLATFORM_LABELS.get(plat, plat),
                "Total registros": len(plat_df),
                "Con promoción": len(plat_promos),
                "% con promoción": f"{len(plat_promos) / len(plat_df) * 100:.0f}%" if len(plat_df) > 0 else "0%",
            })
        st.dataframe(pd.DataFrame(promo_by_plat), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Methodology
# ---------------------------------------------------------------------------

def _render_methodology(df: pd.DataFrame) -> None:
    """Data quality and methodology section for credibility."""
    st.header("Metodología y Calidad de Datos")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
**Fuentes de datos:** Scraping directo de las apps web de Rappi, Uber Eats y DiDi Food
mediante Playwright (browser automation).

**Geografía:** 5 zonas representativas de CDMX, seleccionadas para cubrir variabilidad
socioeconómica: Polanco (premium), Condesa/Roma (alta competencia), Centro Histórico
(alto volumen), Coyoacán (clase media), Iztapalapa (periferia).

**Productos de referencia:**
- **Big Mac** (McDonald's) — producto estandarizado disponible en las 3 plataformas
- **Coca-Cola 600ml** (tienda de conveniencia) — producto retail comparable

**Limitaciones:**
- Los datos son un snapshot puntual, no promedios temporales
- Precios dinámicos pueden variar por hora, día y demanda
- 5 zonas no son estadísticamente significativas para decisiones de pricing en producción
- Anti-bot measures pueden causar datos faltantes o scrapes fallidos
- Promociones personalizadas (basadas en historial) no son capturables sin login
""")

    with col2:
        # Data quality chart
        st.markdown("#### Completitud de datos")
        try:
            fig_quality = chart_data_quality(df)
            st.plotly_chart(fig_quality, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    # Scrape status breakdown
    if not df.empty:
        st.markdown("#### Estado de scraping por plataforma")
        status_pivot = pd.crosstab(
            df["platform"].map(PLATFORM_LABELS).fillna(df["platform"]),
            df["scrape_status"],
            margins=True,
            margins_name="Total",
        )
        st.dataframe(status_pivot, use_container_width=True)

        # Timestamp info
        if "timestamp" in df.columns:
            try:
                ts = pd.to_datetime(df["timestamp"])
                st.caption(
                    f"Datos recolectados entre {ts.min().strftime('%Y-%m-%d %H:%M')} "
                    f"y {ts.max().strftime('%Y-%m-%d %H:%M')} UTC"
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Competitive Intelligence Dashboard")
    st.caption("Rappi vs Uber Eats vs DiDi Food — CDMX, México")

    df_raw = load_data()
    df_filtered, selected_product = render_sidebar(df_raw)

    tab1, tab2 = st.tabs(["Datos & Scraping", "Insights Competitivos"])

    with tab1:
        render_tab_data(df_filtered)

    with tab2:
        render_tab_insights(df_filtered, selected_product)


if __name__ == "__main__":
    main()
