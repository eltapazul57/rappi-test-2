"""
charts.py — Funciones de visualización con Plotly para el dashboard.

Cada función recibe un DataFrame (ya filtrado/procesado) y devuelve
una figura de Plotly lista para renderizar con st.plotly_chart().

Las 3 visualizaciones principales:
1. chart_total_cost_by_zone: precio del producto + delivery fee por zona y plataforma
2. chart_eta_heatmap: ETA (minutos) como heatmap zona × plataforma
3. chart_fee_comparison: comparación de delivery fees por plataforma

Paleta de colores por plataforma (consistente en todos los charts):
    Rappi    → #FF441F  (naranja Rappi)
    Uber Eats → #06C167  (verde Uber Eats)
    DiDi Food → #FF5C35  (naranja DiDi, levemente diferente)
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Paleta de colores consistente para las 3 plataformas
PLATFORM_COLORS: dict[str, str] = {
    "rappi": "#FF441F",
    "uber_eats": "#06C167",
    "didi_food": "#FF5C35",
}

# Nombres legibles para etiquetas en los charts
PLATFORM_LABELS: dict[str, str] = {
    "rappi": "Rappi",
    "uber_eats": "Uber Eats",
    "didi_food": "DiDi Food",
}

ZONE_LABELS: dict[str, str] = {
    "polanco": "Polanco",
    "condesa_roma": "Condesa/Roma",
    "centro_historico": "Centro Histórico",
    "coyoacan": "Coyoacán",
    "iztapalapa": "Iztapalapa",
}


def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepara el DataFrame para visualización:
    - Filtra solo filas con status 'success'
    - Agrega columna 'total_cost' (price + delivery_fee)
    - Agrega etiquetas legibles de plataforma y zona
    """
    df = df[df["scrape_status"] == "success"].copy()
    df["total_cost"] = df["price"].fillna(0) + df["delivery_fee"].fillna(0)
    df["platform_label"] = df["platform"].map(PLATFORM_LABELS).fillna(df["platform"])
    df["zone_label"] = df["zone"].map(ZONE_LABELS).fillna(df["zone"])
    return df


# ---------------------------------------------------------------------------
# Chart 1: Costo total por zona y plataforma
# ---------------------------------------------------------------------------

def chart_total_cost_by_zone(
    df: pd.DataFrame,
    product_key: str = "big_mac",
    title: str | None = None,
) -> go.Figure:
    """
    Gráfico de barras agrupadas: costo total (precio + fee) por zona y plataforma.

    Este es el chart de mayor impacto para el informe de insights porque
    muestra directamente qué plataforma es más cara para el usuario final
    en cada zona geográfica.

    Args:
        df: DataFrame completo (sin filtrar).
        product_key: 'big_mac' o 'coca_cola_600ml'.
        title: título del chart (auto-generado si None).

    Returns:
        Figura Plotly lista para st.plotly_chart().
    """
    # TODO: implementar
    # 1. Filtrar por product_key y status == 'success'
    # 2. Calcular total_cost = price + delivery_fee
    # 3. Usar px.bar() con barmode='group', color='platform_label'
    # 4. Ordenar zonas por la lógica geográfica de norte a sur (polanco → iztapalapa)
    # 5. Agregar anotaciones de precio encima de cada barra
    raise NotImplementedError("chart_total_cost_by_zone no implementado")


# ---------------------------------------------------------------------------
# Chart 2: Heatmap de ETAs por zona × plataforma
# ---------------------------------------------------------------------------

def chart_eta_heatmap(
    df: pd.DataFrame,
    product_key: str = "big_mac",
    title: str | None = None,
) -> go.Figure:
    """
    Heatmap de calor: ETA promedio (minutos) por zona (eje Y) y plataforma (eje X).

    Este chart muestra de forma inmediata qué plataforma es más rápida
    en cada zona. El gradiente de color hace evidente los patrones geográficos.

    Args:
        df: DataFrame completo (sin filtrar).
        product_key: producto a analizar.
        title: título del chart.

    Returns:
        Figura Plotly lista para st.plotly_chart().
    """
    # TODO: implementar
    # 1. Filtrar por product_key y status == 'success'
    # 2. Pivotar: zonas en filas, plataformas en columnas, ETA como valores
    # 3. Usar go.Heatmap() con colorscale='RdYlGn_r' (rojo=lento, verde=rápido)
    # 4. Manejar NaN (not_available) mostrando celda gris con texto "N/D"
    raise NotImplementedError("chart_eta_heatmap no implementado")


# ---------------------------------------------------------------------------
# Chart 3: Comparación de delivery fees
# ---------------------------------------------------------------------------

def chart_fee_comparison(
    df: pd.DataFrame,
    title: str | None = None,
) -> go.Figure:
    """
    Box plot o violin chart: distribución de delivery fees por plataforma
    a lo largo de todas las zonas.

    Este chart muestra la consistencia/variabilidad del fee de cada
    plataforma — una plataforma con fee variable puede estar aplicando
    surge pricing geográfico (insight accionable para Rappi).

    Args:
        df: DataFrame completo (sin filtrar).
        title: título del chart.

    Returns:
        Figura Plotly lista para st.plotly_chart().
    """
    # TODO: implementar
    # 1. Filtrar status == 'success'
    # 2. Usar px.box() o px.violin() con color='platform_label'
    # 3. Agregar puntos individuales (jitter) para ver la distribución real
    # 4. Ordenar plataformas de menor a mayor fee promedio
    raise NotImplementedError("chart_fee_comparison no implementado")


# ---------------------------------------------------------------------------
# Chart bonus: Radar de competitividad por zona
# ---------------------------------------------------------------------------

def chart_competitiveness_radar(
    df: pd.DataFrame,
    zone: str = "polanco",
    title: str | None = None,
) -> go.Figure:
    """
    Radar/spider chart: comparación multidimensional (precio, fee, ETA)
    para una zona específica.

    Chart bonus para el informe de insights — muestra la posición
    competitiva de cada plataforma en múltiples dimensiones simultáneamente.

    Args:
        df: DataFrame completo (sin filtrar).
        zone: zona a analizar (key de config.py).
        title: título del chart.

    Returns:
        Figura Plotly lista para st.plotly_chart().
    """
    # TODO: implementar (opcional — solo si hay tiempo)
    # 1. Filtrar por zona y status == 'success'
    # 2. Normalizar precio, fee y ETA a escala 0-1 (0 = mejor, 1 = peor)
    # 3. Usar go.Scatterpolar() con fill='toself'
    # 4. Una traza por plataforma
    raise NotImplementedError("chart_competitiveness_radar no implementado")
