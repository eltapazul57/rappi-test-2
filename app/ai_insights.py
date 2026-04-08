"""
ai_insights.py - Generación de insights con LLM de OpenAI
"""

from __future__ import annotations

import os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Intentar importar librerías opcionales para IA
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

def is_ai_ready() -> bool:
    """Verifica si openai está instalado y hay una API KEY en .env o entorno."""
    if not HAS_OPENAI:
        return False
    load_dotenv(_ENV_PATH)
    return bool(os.getenv("OPENAI_API_KEY"))

def generate_insights_with_ai(df: pd.DataFrame, context_summary: str = "") -> str:
    """
    Agrega métricas clave del DataFrame y las envía a OpenAI para redactar insights accionables.
    """
    if not is_ai_ready():
        return "La librería openai no está instalada o falta OPENAI_API_KEY en .env."

    load_dotenv(_ENV_PATH)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Filtramos la información relevante para no gastar demasiados tokens
    agg_df = df[df["scrape_status"] == "success"].copy()
    if agg_df.empty:
        return "No hay suficientes datos procesados con estado 'success' para generar insights automáticos."
    
    # Calcular total format
    agg_df["total_cost"] = agg_df["price"].fillna(0) + agg_df["delivery_fee"].fillna(0)
    
    # Resumen principal matemático
    summary_stats = agg_df.groupby(["platform", "zone", "product"])[
        ["price", "delivery_fee", "total_cost", "estimated_time_min"]
    ].mean().round(2).reset_index()
    
    # Conteo de promos para dar insights de descuentos
    promos_count = agg_df.groupby("platform")["promotions"].apply(
        lambda x: (x.notna() & (x.astype(str).str.strip() != "")).sum()
    ).reset_index()

    # Consolidar Contexto de Datos (pasado en la ventana de contexto de GPT)
    data_context = "### Resumen Promediado de Costos y Tiempos (por App, Zona y Producto):\n"
    data_context += f"{summary_stats.to_markdown(index=False)}\n\n"
    data_context += "### Conteo Total de Entregas/Restaurantes con Promociones Activas detectadas:\n"
    data_context += f"{promos_count.to_markdown(index=False)}\n"
    
    if context_summary:
        data_context += f"\n### Contexto Adicional del Usuario u Orquestador:\n{context_summary}\n"

    prompt = f"""
    Eres un Analista Principal de Negocios y Estratega de Pricing para Plataformas de Delivery (Rappi, Uber Eats, DiDi Food).
    Tu objetivo es analizar un extracto de datos competitivos recolectados mediante web scraping y generar los 5 hallazgos accionables más importantes, dirigidos al nivel directivo.

    Datos en crudo del estudio (ya promediados para tu facilidad):
    {data_context}

    Instrucciones formativas:
    1. Basado exhaustivamente en estos números, redacta *exactamente* 5 hallazgos.
    2. Usa lenguaje de negocios, orientado a acciones de crecimiento, logística y fidelización de mercantes y usuarios.
    3. Cada insight debe constar de estos 3 párrafos claramente resaltados (en viñetas):
       - **Hallazgo**: Qué está pasando, sustentado con números explícitos provenientes de la tabla.
       - **Impacto**: Por qué le importa a la cuota de mercado, márgenes, elasticidad o retención.
       - **Recomendación**: Qué debes modificar ya mismo en la app, la estructura de costos de envío o alianzas comerciales.
    4. Sé muy conciso pero contundente; no añadas preludios redundantes. Escribe todo en español neutro. No inventes números fuera de la tabla.
    """

    try:
        response = client.chat.completions.create(
            # Puedes cambiar el modelo en config o dejar `gpt-4o-mini` por defecto por precio-rendimiento
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un brillante consultor de McKinsey analizando pricing dinámico."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2500,
        )
        return response.choices[0].message.content or "La respuesta de IA vino vacía."
    except Exception as exc:
        return f"Error logístico en la comunicación API con OpenAI: {exc}"
