import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

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
                log_area.code("\\n".join(log_lines[-60:]), language="text")

        proc.wait()

        if proc.returncode == 0:
            status_placeholder.success("Scraping completado correctamente. El CSV ha sido actualizado.")
        else:
            status_placeholder.error(f"El scraper terminó con código de error {proc.returncode}. Revisa los logs de arriba.")

    except Exception as exc:
        status_placeholder.error(f"Error iniciando el scraper: {exc}")

    st.cache_data.clear()
    st.rerun()
