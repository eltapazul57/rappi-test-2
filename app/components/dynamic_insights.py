import streamlit as st
import pandas as pd
from app.logic.insights_generator import generate_dynamic_insights

def render_dynamic_insights(df: pd.DataFrame, product_key: str) -> None:
    """Renderiza visualmente la lista de insights generada."""
    insights = generate_dynamic_insights(df, product_key)

    if not insights:
        st.info(
            "No hay suficientes datos para generar hallazgos automáticos. "
            "Ejecuta el scraper para al menos 1 plataforma con datos exitosos."
        )
        return

    for i, insight in enumerate(insights):
        with st.expander(f"Hallazgo {i + 1}: {insight['title']}", expanded=True):
            st.markdown(f"**Hallazgo:** {insight['finding']}")
            st.markdown(f"**Impacto:** {insight['impacto']}")
            st.markdown(f"**Recomendación:** {insight['recomendacion']}")
