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


def chart_price_breakdown(
    df: pd.DataFrame,
    product_key: str = "big_mac",
    title: str | None = None,
) -> go.Figure:
    """Stacked bar: desglose precio producto + delivery fee por zona y plataforma."""
    prepared = _prepare_df(df)
    prepared = prepared[prepared["product"] == product_key]

    if prepared.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos para este producto", showarrow=False)
        return fig

    zone_order_labels = [ZONE_LABELS.get(z, z) for z in ZONE_ORDER if z in prepared["zone"].values]
    prepared["zone_label"] = pd.Categorical(
        prepared["zone_label"], categories=zone_order_labels, ordered=True
    )
    prepared = prepared.sort_values("zone_label")

    # Build one trace per platform for price, one for fee
    platforms = [p for p in ["rappi", "uber_eats", "didi_food"] if p in prepared["platform"].values]

    fig = go.Figure()
    for plat in platforms:
        plat_data = prepared[prepared["platform"] == plat]
        label = PLATFORM_LABELS.get(plat, plat)
        color = PLATFORM_COLORS.get(plat, "#888")

        # Price bar (solid)
        fig.add_trace(go.Bar(
            name=f"{label} — Precio",
            x=plat_data["zone_label"],
            y=plat_data["price"].fillna(0),
            marker_color=color,
            text=plat_data["price"].apply(lambda x: f"${x:.0f}" if pd.notna(x) else ""),
            textposition="inside",
            legendgroup=plat,
        ))
        # Fee bar (lighter, stacked)
        fig.add_trace(go.Bar(
            name=f"{label} — Fee",
            x=plat_data["zone_label"],
            y=plat_data["delivery_fee"].fillna(0),
            marker_color=color,
            marker_opacity=0.45,
            text=plat_data["delivery_fee"].apply(
                lambda x: f"+${x:.0f}" if pd.notna(x) and x > 0 else ("Gratis" if pd.notna(x) and x == 0 else "")
            ),
            textposition="inside",
            legendgroup=plat,
        ))

    product_name = {"big_mac": "Big Mac", "coca_cola_600ml": "Coca-Cola 600ml"}.get(product_key, product_key)
    fig.update_layout(
        barmode="stack",
        title=title or f"Desglose de Costo — {product_name}",
        xaxis_title="",
        yaxis_title="MXN",
        legend_title="Componente",
        height=450,
    )

    return fig


def chart_data_quality(df: pd.DataFrame, title: str | None = None) -> go.Figure:
    """Stacked bar showing data completeness per column across platforms."""
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos", showarrow=False)
        return fig

    success_df = df[df["scrape_status"] == "success"].copy()
    if success_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos exitosos", showarrow=False)
        return fig

    columns_to_check = ["price", "delivery_fee", "estimated_time_min", "promotions"]
    platforms = [p for p in ["rappi", "uber_eats", "didi_food"] if p in success_df["platform"].values]

    data_rows = []
    for plat in platforms:
        plat_df = success_df[success_df["platform"] == plat]
        total = len(plat_df)
        for col in columns_to_check:
            if col == "promotions":
                filled = plat_df[col].notna() & (plat_df[col].astype(str).str.strip() != "")
            else:
                filled = plat_df[col].notna()
            pct = filled.sum() / total * 100 if total > 0 else 0
            col_label = {
                "price": "Precio",
                "delivery_fee": "Delivery Fee",
                "estimated_time_min": "ETA",
                "promotions": "Promociones",
            }.get(col, col)
            data_rows.append({
                "platform": PLATFORM_LABELS.get(plat, plat),
                "column": col_label,
                "pct_filled": pct,
                "color": PLATFORM_COLORS.get(plat, "#888"),
            })

    plot_df = pd.DataFrame(data_rows)

    color_map = {PLATFORM_LABELS[k]: v for k, v in PLATFORM_COLORS.items() if k in success_df["platform"].values}

    fig = px.bar(
        plot_df,
        x="column",
        y="pct_filled",
        color="platform",
        barmode="group",
        color_discrete_map=color_map,
        text=plot_df["pct_filled"].apply(lambda x: f"{x:.0f}%"),
        labels={"column": "Métrica", "pct_filled": "% Completitud", "platform": "Plataforma"},
        title=title or "Completitud de Datos por Métrica",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        yaxis_range=[0, 110],
        height=350,
        xaxis_title="",
        yaxis_title="% de filas con dato",
    )
    return fig
