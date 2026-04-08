import pandas as pd
import streamlit as st

from app.components.dynamic_insights import render_dynamic_insights
from app.ai_insights import generate_insights_with_ai, is_ai_ready
from app.charts import (
    PLATFORM_LABELS,
    PRODUCT_LABELS,
    ZONE_LABELS,
    chart_total_cost_by_zone,
    chart_eta_heatmap,
    chart_price_by_product,
    chart_price_breakdown,
    chart_data_quality,
)

def render_tab_insights(df: pd.DataFrame, selected_product: str) -> None:
    st.title("Informe de Inteligencia Competitiva")
    st.caption("Análisis comparativo: Rappi vs Uber Eats vs DiDi Food — CDMX, México")

    success_df = df[df["scrape_status"] == "success"].copy() if not df.empty else df

    if success_df.empty:
        st.warning("No hay datos exitosos para mostrar insights. Ejecuta el scraper primero.")
        return

    # ── Executive Summary ─────────────────────────────────────────────
    _render_executive_summary(success_df, selected_product)

    st.divider()

    # ── Top 5 Insights ────────────────────────────────────────────────
    st.header("5 Hallazgos Competitivos Principales")
    st.markdown(
        "Hallazgos calculados a partir de los datos recolectados. "
        "Cada hallazgo incluye descripción, impacto al negocio y recomendación."
    )
    render_dynamic_insights(success_df, selected_product)

    st.divider()

    # ── Visualizaciones ───────────────────────────────────────────────
    st.header("Visualizaciones Comparativas")

    product_name = PRODUCT_LABELS.get(selected_product, selected_product)

    # Chart 1: Total cost by zone (full width)
    st.markdown(f"#### 1. Costo Total al Usuario por Zona -- {product_name}")
    try:
        fig1 = chart_total_cost_by_zone(df, product_key=selected_product)
        st.plotly_chart(fig1, use_container_width=True)
    except Exception as exc:
        st.error(f"Error generando grafica: {exc}")

    # Charts 2 & 3 side by side
    col_c2, col_c3 = st.columns(2)

    with col_c2:
        st.markdown(f"#### 2. Tiempo de Entrega por Zona -- {product_name}")
        try:
            fig2 = chart_eta_heatmap(df, product_key=selected_product)
            st.plotly_chart(fig2, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    with col_c3:
        st.markdown("#### 3. Precio Promedio por Producto (todas las zonas)")
        try:
            fig3 = chart_price_by_product(df)
            st.plotly_chart(fig3, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    # Chart 4: Price breakdown (full width)
    st.markdown(f"#### 4. Desglose de Costo: Producto vs Envío — {product_name}")
    try:
        fig4 = chart_price_breakdown(df, product_key=selected_product)
        st.plotly_chart(fig4, use_container_width=True)
    except Exception as exc:
        st.error(f"Error: {exc}")

    st.divider()

    # ── Promotions analysis ───────────────────────────────────────────
    _render_promotions_analysis(success_df)

    st.divider()

    # ── Methodology ───────────────────────────────────────────────────
    _render_methodology(df)

    st.divider()

    # ── AI Insights (opcional) ────────────────────────────────────────
    with st.expander("Análisis con IA"):
        if is_ai_ready():
            st.markdown(
                "Genera un análisis estratégico adicional alimentando un LLM "
                "con los datos recolectados."
            )
            if st.button("Generar Hallazgos con IA"):
                with st.spinner("Consultando modelo..."):
                    ai_markdown = generate_insights_with_ai(success_df)
                    st.markdown(ai_markdown)
        else:
            st.info(
                "Para activar esta funcionalidad, configura la variable OPENAI_API_KEY en el "
                "archivo .env. Consulta .env.example como referencia."
            )


def _render_executive_summary(df: pd.DataFrame, product_key: str) -> None:
    """KPI cards + one-paragraph summary at the top of the insights tab."""
    st.header("Resumen Ejecutivo")

    platforms = df["platform"].unique()
    zones = df["zone"].unique()
    n_success = len(df)

    df = df.copy()
    df["total_cost"] = df["price"].fillna(0) + df["delivery_fee"].fillna(0)

    avg_price = df["price"].mean()
    avg_eta = df["estimated_time_min"].mean()

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
            f"El costo de envío fue capturado en {fee_pct:.0f}% de los registros — "
            f"las zonas sin dato pueden indicar envío gratis o limitaciones del scraper."
        )

    st.markdown(
        f"Este informe analiza datos de **{platform_names}** en **{len(zones)} zonas de CDMX** "
        f"({zone_names}). "
        + " ".join(summary_parts)
    )


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


def _render_methodology(df: pd.DataFrame) -> None:
    """Data quality and methodology section for credibility."""
    st.header("Metodología y Calidad de Datos")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
**Fuentes de datos:** Scraping directo de las apps web de Rappi, Uber Eats y DiDi Food
mediante Playwright (browser automation).

**Geografia:** 5 zonas representativas de CDMX, seleccionadas para cubrir variabilidad
socioeconomica: Polanco (premium), Condesa/Roma (alta competencia), Centro Historico
(alto volumen), Coyoacan (clase media), Iztapalapa (periferia).

**Productos de referencia:**
- **Big Mac** (McDonald's) -- producto estandarizado, categoria restaurante
- **Whopper** (Burger King) -- producto estandarizado, categoria restaurante
- **Pizza Pepperoni** -- producto de cadena, categoria restaurante
- **Coca-Cola 600ml** (tienda / conveniencia) -- producto retail comparable
- **Coca-Cola 600ml 7-Eleven** -- mismo producto, canal convenience store

**Limitaciones:**
- Los datos son un snapshot puntual, no promedios temporales
- Precios dinamicos pueden variar por hora, dia y demanda
- 5 zonas no son estadisticamente significativas para decisiones de pricing en produccion
- Medidas anti-bot pueden causar datos faltantes o scrapes fallidos
- Promociones personalizadas (basadas en historial) no son capturables sin login
- DiDi Food no resuelve DNS; todos sus registros aparecen como not_available
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
