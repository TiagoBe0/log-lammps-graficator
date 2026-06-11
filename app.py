"""LAMMPS Log Graficator — app web para graficar logs de LAMMPS.

Arrastra y solta uno o mas logs, elegi que columnas thermo graficar y mira
las metricas de computo (ns/day, %CPU, desglose MPI, memoria) de cada run.

Correr con:  streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lammps_log_parser import LammpsLog, parse_log, runs_summary

st.set_page_config(page_title="LAMMPS Log Graficator", page_icon="📈", layout="wide")

MAX_POINTS_PER_TRACE = 10_000
# Formatos de imagen que ofrece el boton de camara del grafico (export en el
# navegador, sin dependencias en el servidor). Etiqueta -> formato de Plotly.
IMG_FORMATS = {"PNG": "png", "JPG": "jpeg", "SVG (vectorial)": "svg"}
DEFAULT_IMG_FORMAT = "PNG"


def plot_config(filename: str = "lammps_plot") -> dict:
    """Config de Plotly con el formato de imagen elegido para el boton de camara."""
    fmt = IMG_FORMATS.get(st.session_state.get("img_fmt", DEFAULT_IMG_FORMAT), "png")
    return {
        "displaylogo": False,
        "toImageButtonOptions": {"format": fmt, "scale": 3, "filename": filename},
    }

# Fuente con aire a publicacion cientifica (serif, tipo Computer Modern/Times).
PAPER_FONT = "Georgia, 'Times New Roman', 'Nimbus Roman', serif"
# Paleta Okabe-Ito: segura para daltonismo y habitual en figuras de papers.
PAPER_PALETTE = [
    "#0072B2", "#D55E00", "#009E73", "#CC79A7",
    "#E69F00", "#56B4E9", "#F0E442", "#000000",
]

# Tres fondos seleccionables. "Gris" es el de por defecto.
THEMES = {
    "Gris": {
        "page_bg": "#4b4f57",
        "page_text": "#f3f4f6",
        "panel_bg": "#5a5f69",
        "paper_bg": "#ffffff",   # la figura es una tarjeta blanca tipo paper
        "plot_bg": "#ffffff",
        "font_color": "#1a1a1a",
        "grid": "rgba(0,0,0,0.12)",
        "axis": "#33373d",
    },
    "Claro": {
        "page_bg": "#fafafa",
        "page_text": "#1a1a1a",
        "panel_bg": "#ffffff",
        "paper_bg": "#ffffff",
        "plot_bg": "#ffffff",
        "font_color": "#1a1a1a",
        "grid": "rgba(0,0,0,0.12)",
        "axis": "#33373d",
    },
    "Oscuro": {
        "page_bg": "#15171c",
        "page_text": "#e8eaed",
        "panel_bg": "#1f222a",
        "paper_bg": "#1f222a",
        "plot_bg": "#1f222a",
        "font_color": "#e8eaed",
        "grid": "rgba(255,255,255,0.14)",
        "axis": "#b8bcc4",
    },
}
DEFAULT_THEME = "Gris"


def current_theme() -> dict:
    return THEMES.get(st.session_state.get("theme_name", DEFAULT_THEME), THEMES[DEFAULT_THEME])


def inject_theme_css(theme: dict) -> None:
    """Pinta el fondo de la app y fuerza el color de TODO el texto sobre el.

    Solo toca texto que vive directamente sobre el fondo de la pagina/sidebar
    (titulos, markdown, labels, tabs, metricas, expanders, radios/checkboxes).
    NO toca inputs ni tablas: esos tienen su propio fondo claro y texto oscuro,
    asi que se leen bien en cualquier tema.
    """
    t = theme["page_text"]
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {theme['page_bg']}; color: {t}; }}
        [data-testid="stSidebar"] > div:first-child {{ background-color: {theme['panel_bg']}; }}
        [data-testid="stHeader"] {{ background-color: rgba(0,0,0,0); }}

        /* Texto que vive sobre el fondo de la pagina/sidebar */
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] strong,
        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] div,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] *,
        [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"],
        .stTabs [data-baseweb="tab"],
        .stTabs [data-baseweb="tab"] p,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary span,
        [data-testid="stExpander"] summary p,
        [role="radiogroup"] label,
        [data-testid="stCheckbox"] label,
        [data-testid="stRadio"] label
        {{ color: {t} !important; fill: {t} !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner="Parseando log...")
def cached_parse(content: bytes) -> LammpsLog:
    return parse_log(content.decode(errors="replace"))


def decimate(df: pd.DataFrame, max_points: int = MAX_POINTS_PER_TRACE) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    return df.iloc[:: len(df) // max_points + 1]


def style_figure(fig: go.Figure, height: int = 600) -> go.Figure:
    """Aplica estetica de paper cientifico, respetando el tema activo.

    Caracteristicas: tipografia serif, paleta apta para daltonismo, ejes con
    marco (box) y ticks hacia afuera, y SIEMPRE grilla en X e Y.
    """
    theme = current_theme()
    fig.update_layout(
        template="plotly_white" if theme["plot_bg"] != "#1f222a" else "plotly_dark",
        height=height,
        paper_bgcolor=theme["paper_bg"],
        plot_bgcolor=theme["plot_bg"],
        font=dict(family=PAPER_FONT, size=15, color=theme["font_color"]),
        colorway=PAPER_PALETTE,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=50, r=20),
        title=dict(font=dict(family=PAPER_FONT, size=17, color=theme["font_color"]), x=0.01),
    )
    axis_kwargs = dict(
        showgrid=True,
        gridcolor=theme["grid"],
        gridwidth=1,
        griddash="dot",
        zeroline=False,
        showline=True,
        linecolor=theme["axis"],
        linewidth=1.4,
        mirror=True,
        ticks="outside",
        tickcolor=theme["axis"],
        ticklen=6,
        tickfont=dict(family=PAPER_FONT, color=theme["font_color"]),
        title_font=dict(family=PAPER_FONT, color=theme["font_color"]),
    )
    fig.update_xaxes(**axis_kwargs)
    fig.update_yaxes(**axis_kwargs)
    # Titulos de subplots (anotaciones) acordes al tema y a la tipografia.
    fig.update_annotations(font=dict(family=PAPER_FONT, color=theme["font_color"]))
    return fig


def show_figure(fig: go.Figure, download_name: str) -> None:
    st.plotly_chart(fig, width="stretch", config=plot_config(download_name))
    img_fmt = st.session_state.get("img_fmt", DEFAULT_IMG_FORMAT)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.caption(
            f"🖼️ **Descargar imagen ({img_fmt}):** pasa el mouse por el grafico y "
            f"clickea el icono de camara 📷 (arriba a la derecha)."
        )
    with c2:
        st.download_button(
            "⬇️ Descargar grafico interactivo (HTML)",
            fig.to_html(include_plotlyjs="cdn"),
            file_name=f"{download_name}.html",
            mime="text/html",
            help="Archivo standalone: se abre en cualquier navegador, ideal para compartir.",
        )


# -----------------------------------------------------------------------------
st.sidebar.radio(
    "🎨 Fondo",
    list(THEMES),
    index=list(THEMES).index(DEFAULT_THEME),
    horizontal=True,
    key="theme_name",
    help="Elegi el color de fondo de la app (gris por defecto).",
)
inject_theme_css(current_theme())
st.sidebar.radio(
    "🖼️ Formato de imagen",
    list(IMG_FORMATS),
    index=list(IMG_FORMATS).index(DEFAULT_IMG_FORMAT),
    horizontal=True,
    key="img_fmt",
    help="Formato del boton de camara 📷 que descarga cada grafico como imagen.",
)
st.sidebar.divider()

st.title("📈 LAMMPS Log Graficator")

uploaded = st.sidebar.file_uploader(
    "Arrastra y solta tus logs de LAMMPS",
    accept_multiple_files=True,
    help="Acepta log.lammps, *.log, *.txt... Podes subir varios para compararlos.",
)

if not uploaded:
    st.info(
        "👈 **Arrastra y solta** uno o mas logs de LAMMPS en la barra lateral "
        "para empezar.\n\n"
        "- **Termodinamica**: elegi columnas thermo (Temp, Press, TotEng, "
        "computes, variables...) y graficalas con calidad de publicacion.\n"
        "- **Computo**: ns/day, timesteps/s, %CPU, memoria por rank y desglose "
        "de tiempos MPI de cada run.\n"
        "- Subi **varios logs a la vez** para comparar simulaciones.\n"
        "- Tambien funciona con logs de simulaciones **todavia corriendo**."
    )
    st.stop()

logs = {f.name: cached_parse(f.getvalue()) for f in uploaded}
logs = {name: log for name, log in logs.items() if log.runs}
sin_runs = [f.name for f in uploaded if f.name not in logs]
if sin_runs:
    st.warning(f"Sin datos thermo (no parecen logs de LAMMPS): {', '.join(sin_runs)}")
if not logs:
    st.stop()

tab_thermo, tab_compute, tab_info = st.tabs(
    ["📊 Termodinamica", "⚙️ Computo", "ℹ️ Info del log"]
)

# ============================================================ TERMODINAMICA ==
with tab_thermo:
    sel_files = st.multiselect(
        "Logs a graficar", list(logs), default=list(logs),
    )
    if not sel_files:
        st.stop()

    max_runs = max(len(logs[f].runs) for f in sel_files)
    run_options = list(range(1, max_runs + 1))
    if len(sel_files) == 1:
        labels = {r.index + 1: r.label for r in logs[sel_files[0]].runs}
    else:
        labels = {i: f"Run {i}" for i in run_options}
    sel_runs = st.multiselect(
        "Runs (cada comando `run`/`minimize` del script es un run)",
        run_options,
        default=run_options,
        format_func=lambda i: labels.get(i, f"Run {i}"),
    )

    all_cols: list[str] = []
    for f in sel_files:
        for run in logs[f].runs:
            if run.index + 1 in sel_runs:
                for c in run.columns:
                    if c not in all_cols:
                        all_cols.append(c)

    if not all_cols:
        st.warning("Los runs seleccionados no tienen datos.")
        st.stop()

    c1, c2 = st.columns([1, 3])
    with c1:
        x_col = st.selectbox(
            "Eje X", all_cols, index=all_cols.index("Step") if "Step" in all_cols else 0
        )
    with c2:
        default_y = [c for c in ("Temp",) if c in all_cols] or all_cols[1:2]
        y_cols = st.multiselect("Columnas a graficar (eje Y)", all_cols, default=default_y)

    with st.expander("⚙️ Opciones del grafico"):
        o1, o2, o3 = st.columns(3)
        with o1:
            modo = st.radio(
                "Disposicion", ["Un solo grafico", "Subplot por columna"], key="disposicion"
            )
            unir_runs = st.checkbox(
                "Unir runs en una sola curva", value=True,
                help="Concatena los runs seleccionados; util cuando un protocolo "
                "tiene varias etapas (minimizacion, NVT, NPT...).",
            )
        with o2:
            ventana = st.slider(
                "Suavizado (media movil, puntos)", 1, 201, 1, step=2,
                help="1 = sin suavizado",
            )
            mostrar_crudo = st.checkbox("Mostrar datos crudos detras del suavizado", value=True)
        with o3:
            log_y = st.checkbox("Escala log en Y")
            marcadores = st.checkbox("Mostrar puntos")

    if not y_cols:
        st.info("Elegi al menos una columna para graficar.")
        st.stop()

    # --- Armar series: una por (archivo, run|unido, columna) ---
    series = []  # (nombre_traza, df, columna)
    multi_file = len(sel_files) > 1
    for f in sel_files:
        runs = [r for r in logs[f].runs if r.index + 1 in sel_runs]
        grupos = (
            [("", pd.concat([r.df for r in runs], ignore_index=True))]
            if unir_runs and runs
            else [(r.label, r.df) for r in runs]
        )
        for run_label, df in grupos:
            if x_col not in df.columns:
                continue
            df = df.sort_values(x_col)
            for col in y_cols:
                if col not in df.columns:
                    continue
                parts = [col] + ([run_label] if run_label else []) + ([f] if multi_file else [])
                series.append((" · ".join(parts), df, col))

    if not series:
        st.warning(f"Ninguna de las columnas elegidas aparece junto a '{x_col}' en los runs seleccionados.")
        st.stop()

    n_filas = len(y_cols) if modo == "Subplot por columna" else 1
    fig = make_subplots(
        rows=n_filas, cols=1, shared_xaxes=True,
        subplot_titles=y_cols if n_filas > 1 else None, vertical_spacing=0.06,
    )
    line_mode = "lines+markers" if marcadores else "lines"
    for name, df, col in series:
        row = y_cols.index(col) + 1 if n_filas > 1 else 1
        df = decimate(df[[x_col, col]].dropna())
        y = df[col]
        if ventana > 1:
            suave = y.rolling(ventana, center=True, min_periods=1).mean()
            if mostrar_crudo:
                fig.add_scatter(
                    x=df[x_col], y=y, mode="lines", line=dict(width=1),
                    opacity=0.25, showlegend=False, hoverinfo="skip", row=row, col=1,
                )
            y = suave
        fig.add_scatter(x=df[x_col], y=y, mode=line_mode, name=name, row=row, col=1)

    fig.update_xaxes(title_text=x_col, row=n_filas, col=1)
    if n_filas == 1 and len(y_cols) == 1:
        fig.update_yaxes(title_text=y_cols[0])
    if log_y:
        fig.update_yaxes(type="log")
    style_figure(fig, height=max(550, 280 * n_filas))
    show_figure(fig, "lammps_thermo")

    with st.expander("📄 Datos seleccionados / descargar CSV"):
        partes = []
        for f in sel_files:
            for run in logs[f].runs:
                if run.index + 1 in sel_runs:
                    df = run.df.copy()
                    df.insert(0, "run", run.index + 1)
                    if multi_file:
                        df.insert(0, "archivo", f)
                    partes.append(df)
        datos = pd.concat(partes, ignore_index=True)
        st.dataframe(datos, height=300)
        st.download_button(
            "⬇️ Descargar CSV", datos.to_csv(index=False).encode(),
            file_name="lammps_thermo.csv", mime="text/csv",
        )

# ================================================================== COMPUTO ==
with tab_compute:
    fname = (
        st.selectbox("Log", list(logs)) if len(logs) > 1 else list(logs)[0]
    )
    log = logs[fname]
    completos = [r for r in log.runs if r.complete]
    principal = max(completos, key=lambda r: r.loop_time or 0, default=None)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Wall time total", log.total_wall_time or "— (corriendo?)")
    m2.metric("Runs", len(log.runs))
    if principal:
        m3.metric("Atomos", f"{principal.n_atoms:,}")
        m4.metric("MPI x OpenMP", f"{principal.mpi_tasks} x {principal.omp_threads}")
        if "ns/day" in principal.performance:
            m5.metric("ns/day (run principal)", principal.performance["ns/day"])

    st.subheader("Resumen por run")
    st.dataframe(runs_summary(log), hide_index=True)

    if completos:
        g1, g2 = st.columns(2)
        perf_df = pd.DataFrame(
            {
                "Run": [f"Run {r.index + 1}" for r in completos],
                "ns/day": [r.performance.get("ns/day") for r in completos],
                "%CPU": [r.cpu_use for r in completos],
                "Memoria avg (MB)": [r.memory_mb[1] if r.memory_mb else None for r in completos],
            }
        )
        with g1:
            fig = px.bar(perf_df.dropna(subset=["ns/day"]), x="Run", y="ns/day",
                         title="Rendimiento por run")
            st.plotly_chart(style_figure(fig, 400), width="stretch", config=plot_config("ns_por_dia"))
        with g2:
            fig = px.bar(perf_df, x="Run", y="%CPU", title="% de uso de CPU por run")
            fig.update_yaxes(range=[0, 105])
            st.plotly_chart(style_figure(fig, 400), width="stretch", config=plot_config("uso_cpu"))

        # Desglose MPI: en que se va el tiempo (Pair, Comm, Neigh...)
        partes = []
        for r in completos:
            if r.mpi_breakdown is not None and not r.mpi_breakdown.empty:
                bd = r.mpi_breakdown[["Seccion", "%total"]].copy()
                bd["Run"] = f"Run {r.index + 1}"
                partes.append(bd)
        g3, g4 = st.columns(2)
        with g3:
            if partes:
                bd = pd.concat(partes, ignore_index=True)
                fig = px.bar(
                    bd, x="Run", y="%total", color="Seccion",
                    title="Desglose de tiempos MPI (% del loop time)",
                )
                st.plotly_chart(style_figure(fig, 420), width="stretch", config=plot_config("desglose_mpi"))
        with g4:
            fig = px.bar(perf_df.dropna(subset=["Memoria avg (MB)"]),
                         x="Run", y="Memoria avg (MB)", title="Memoria por rank MPI")
            st.plotly_chart(style_figure(fig, 420), width="stretch", config=plot_config("memoria"))

    # --- Comparacion entre logs ---
    if len(logs) > 1:
        st.subheader("Comparacion entre logs (run mas largo de cada uno)")
        comp = []
        for name, lg in logs.items():
            r = max((x for x in lg.runs if x.complete), key=lambda x: x.loop_time or 0, default=None)
            if r:
                comp.append(
                    {
                        "Log": name,
                        "ns/day": r.performance.get("ns/day"),
                        "timesteps/s": r.performance.get("timesteps/s"),
                        "%CPU": r.cpu_use,
                        "Loop time (s)": r.loop_time,
                        "Atomos": r.n_atoms,
                    }
                )
        comp_df = pd.DataFrame(comp)
        st.dataframe(comp_df, hide_index=True)
        if comp_df["ns/day"].notna().any():
            fig = px.bar(comp_df, x="Log", y="ns/day", title="ns/day por log")
            st.plotly_chart(style_figure(fig, 400), width="stretch", config=plot_config("ns_por_dia_por_log"))

# ===================================================================== INFO ==
with tab_info:
    for name, lg in logs.items():
        with st.expander(f"📄 {name}", expanded=len(logs) == 1):
            st.markdown(
                f"**Version:** {lg.version or 'desconocida'}  \n"
                f"**Wall time total:** {lg.total_wall_time or 'no termino (corriendo o interrumpido)'}  \n"
                f"**Runs:** {len(lg.runs)}"
            )
            incompletos = [r.label for r in lg.runs if not r.complete]
            if incompletos:
                st.warning("Runs incompletos (simulacion corriendo o cortada): " + ", ".join(incompletos))
            if lg.warnings:
                st.markdown(f"**Warnings ({len(lg.warnings)}):**")
                st.code("\n".join(dict.fromkeys(lg.warnings)), language=None)
