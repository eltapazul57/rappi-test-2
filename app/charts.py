"""
charts.py — Visualizaciones Plotly para el dashboard.

3 charts principales:
1. chart_total_cost_by_zone: barras agrupadas de costo total por zona y plataforma
2. chart_eta_heatmap: heatmap de ETA zona × plataforma
3. chart_fee_comparison: box plot de delivery fees por plataforma
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

PLATFORM_COLORS: dict[str, str] = {
    "rappi": "#FF441F",
    "uber_eats": "#06C167",
    "didi_food": "#FF8C00",
}

PLATFORM_LABELS: dict[str, str] = {
    "rappi": "Rappi",
    "uber_eats": "Uber Eats",
    "didi_food": "DiDi Food",
}

# Orden geográfico norte → sur
ZONE_ORDER: list[str] = [
    "polanco",
    "condesa_roma",
    "centro_historico",
    "coyoacan",
    "iztapalapa",
]

ZONE_LABELS: dict[str, str] = {
    "polanco": "Polanco",
    "condesa_roma": "Condesa/Roma",
    "centro_historico": "Centro Histórico",
    "coyoacan": "Coyoacán",
    "iztapalapa": "Iztapalapa",
}


def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra success, agrega total_cost y etiquetas legibles."""
    df = df[df["scrape_status"] == "success"].copy()
    df["total_cost"] = df["price"].fillna(0) + df["delivery_fee"].fillna(0)
    df["platform_label"] = df["platform"].map(PLATFORM_LABELS).fillna(df["platform"])
    df["zone_label"] = df["zone"].map(ZONE_LABELS).fillna(df["zone"])
    return df


def chart_total_cost_by_zone(
    df: pd.DataFrame,
    product_key: str = "big_mac",
    title: str | None = None,
) -> go.Figure:
    """Barras agrupadas: costo total (precio + fee) por zona y plataforma."""
    prepared = _prepare_df(df)
    prepared = prepared[prepared["product"] == product_key]

    if prepared.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos para este producto", showarrow=False)
        return fig

    # Ordenar zonas geográficamente
    zone_order_labels = [ZONE_LABELS.get(z, z) for z in ZONE_ORDER if z in prepared["zone"].values]
    prepared["zone_label"] = pd.Categorical(
        prepared["zone_label"], categories=zone_order_labels, ordered=True
    )
    prepared = prepared.sort_values("zone_label")

    color_map = {PLATFORM_LABELS[k]: v for k, v in PLATFORM_COLORS.items() if k in prepared["platform"].values}

    product_name = {"big_mac": "Big Mac", "coca_cola_600ml": "Coca-Cola 600ml"}.get(product_key, product_key)

    fig = px.bar(
        prepared,
        x="zone_label",
        y="total_cost",
        color="platform_label",
        barmode="group",
        color_discrete_map=color_map,
        text=prepared["total_cost"].apply(lambda x: f"${x:.0f}"),
        labels={
            "zone_label": "Zona",
            "total_cost": "Costo Total (MXN)",
            "platform_label": "Plataforma",
        },
        title=title or f"Costo Total al Usuario — {product_name}",
    )

    fig.update_traces(textposition="outside")
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Costo Total (MXN)",
        legend_title="Plataforma",
        height=450,
    )

    return fig


def chart_eta_heatmap(
    df: pd.DataFrame,
    product_key: str = "big_mac",
    title: str | None = None,
) -> go.Figure:
    """Heatmap: ETA (minutos) por zona (Y) y plataforma (X)."""
    prepared = _prepare_df(df)
    prepared = prepared[prepared["product"] == product_key]

    if prepared.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos para este producto", showarrow=False)
        return fig

    pivot = prepared.pivot_table(
        values="estimated_time_min",
        index="zone",
        columns="platform",
        aggfunc="mean",
    )

    # Ordenar zonas y plataformas
    zone_order_filtered = [z for z in ZONE_ORDER if z in pivot.index]
    pivot = pivot.reindex(index=zone_order_filtered)

    platform_order = [p for p in ["rappi", "uber_eats", "didi_food"] if p in pivot.columns]
    pivot = pivot[platform_order]

    # Labels legibles
    y_labels = [ZONE_LABELS.get(z, z) for z in pivot.index]
    x_labels = [PLATFORM_LABELS.get(p, p) for p in pivot.columns]

    # Texto para cada celda
    text_matrix = pivot.copy()
    text_matrix = text_matrix.map(
        lambda v: f"{v:.0f} min" if pd.notna(v) else "N/D"
    )

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=x_labels,
        y=y_labels,
        text=text_matrix.values,
        texttemplate="%{text}",
        colorscale="RdYlGn_r",  # rojo=lento, verde=rápido
        hoverongaps=False,
        colorbar=dict(title="Minutos"),
    ))

    product_name = {"big_mac": "Big Mac", "coca_cola_600ml": "Coca-Cola 600ml"}.get(product_key, product_key)

    fig.update_layout(
        title=title or f"Tiempo de Entrega — {product_name}",
        xaxis_title="",
        yaxis_title="",
        height=400,
    )

    return fig


def chart_fee_comparison(
    df: pd.DataFrame,
    title: str | None = None,
) -> go.Figure:
    """Box plot: distribución de delivery fees por plataforma."""
    prepared = _prepare_df(df)
    prepared = prepared.dropna(subset=["delivery_fee"])

    if prepared.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos de delivery fee", showarrow=False)
        return fig

    color_map = {PLATFORM_LABELS[k]: v for k, v in PLATFORM_COLORS.items() if k in prepared["platform"].values}

    fig = px.box(
        prepared,
        x="platform_label",
        y="delivery_fee",
        color="platform_label",
        color_discrete_map=color_map,
        points="all",
        labels={
            "platform_label": "Plataforma",
            "delivery_fee": "Delivery Fee (MXN)",
        },
        title=title or "Distribución de Delivery Fees",
    )

    fig.update_layout(
        xaxis_title="",
        yaxis_title="Fee (MXN)",
        showlegend=False,
        height=400,
    )

    return fig
