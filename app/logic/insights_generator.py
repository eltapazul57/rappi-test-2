import pandas as pd
from app.charts import PLATFORM_LABELS, PRODUCT_LABELS, ZONE_LABELS

def generate_dynamic_insights(df: pd.DataFrame, product_key: str) -> list[dict]:
    """Calcula insights basados en los datos reales y devuelve una lista de diccionarios."""
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
                    f"Los usuarios sensibles al precio migrarán hacia {PLATFORM_LABELS.get(cheapest, cheapest)}. "
                    f"Una diferencia del {pct_diff:.0f}% en costo total impacta directamente la tasa de conversión "
                    f"y la cuota de mercado en zonas competidas."
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
                    "title": "Variabilidad geográfica del costo de envío",
                    "finding": (
                        f"{PLATFORM_LABELS.get(most_variable, most_variable)} tiene el costo de envío más variable: "
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
                "title": f"Patrón de costo de envío en {PLATFORM_LABELS.get(plat, plat)}",
                "finding": (
                    f"El costo de envío de {PLATFORM_LABELS.get(plat, plat)} promedia ${stats['mean']:.0f} MXN "
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

    return insights
