import math
import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE = os.getenv("REST_API_URL", "http://rest_api:5000")

# Tendencias: siempre 30 puntos por variable y grilla de 2 columnas
PUNTOS_SERIE = 30
COLUMNAS_TENDENCIA = 2

st.title("Monitoreo minero — Zona Sur Calderón Kramarenko")
st.caption("Últimas 20 lecturas MQTT (mina/zona_sur_calderon_kramarenko/…) en MongoDB")

_TOPIC_META_KEYS = frozenset(
    {
        "_id",
        "mqtt_topic",
        "zona_topic",
        "sensor_topic",
        "timestamp",
        "zona",
        "sensor",
    }
)


def _es_valor_vacio(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _lecturas_a_formato_largo(docs: list) -> list[dict]:
    """Una fila por cada par (nombre de medición, valor), con tópicos repetidos."""
    filas: list[dict] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        base = {
            k: doc[k]
            for k in ("timestamp", "zona_topic", "sensor_topic", "mqtt_topic")
            if k in doc
        }
        for clave in sorted(doc.keys()):
            if clave in _TOPIC_META_KEYS or clave == "_id":
                continue
            valor = doc[clave]
            if _es_valor_vacio(valor):
                continue
            filas.append({**base, "variable": clave, "valor": valor})
    return filas


def _docs_a_filas_una_variable(docs: list, variable: str) -> list[dict]:
    """Una fila por lectura, solo la variable elegida."""
    filas: list[dict] = []
    for doc in docs:
        if not isinstance(doc, dict) or variable not in doc:
            continue
        valor = doc[variable]
        if _es_valor_vacio(valor):
            continue
        base = {
            k: doc[k]
            for k in ("timestamp", "zona_topic", "sensor_topic", "mqtt_topic")
            if k in doc
        }
        filas.append({**base, "variable": variable, "valor": valor})
    return filas


def _fetch_json_list(url: str, params=None) -> tuple[list | None, str | None]:
    try:
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
        if res.status_code >= 400:
            msg = data.get("error", res.text) if isinstance(data, dict) else res.text
            return None, str(msg)
        if isinstance(data, dict) and "error" in data:
            return None, str(data["error"])
        if not isinstance(data, list):
            return None, "Respuesta inesperada del servidor"
        return data, None
    except Exception as e:
        return None, str(e)


def _fetch_variables() -> list[str]:
    data, err = _fetch_json_list(f"{API_BASE}/variables")
    if err or data is None:
        return []
    return sorted(str(v) for v in data if v)


def _fetch_series(variables: list[str], limit: int) -> tuple[dict | None, str | None]:
    if not variables:
        return {}, None
    try:
        res = requests.get(
            f"{API_BASE}/series",
            params={"variables": ",".join(variables), "limit": limit},
            timeout=30,
        )
        data = res.json()
        if res.status_code >= 400:
            msg = data.get("error", res.text) if isinstance(data, dict) else res.text
            return None, str(msg)
        if isinstance(data, dict) and "error" in data:
            return None, str(data["error"])
        if not isinstance(data, dict):
            return None, "Respuesta inesperada del servidor (/series)"
        return data, None
    except Exception as e:
        return None, str(e)


def _mostrar_tabla(filas: list[dict]) -> None:
    if not filas:
        st.info("No hay filas para mostrar con el filtro actual.")
        return
    df = pd.DataFrame(filas)
    orden = [
        c
        for c in (
            "timestamp",
            "zona_topic",
            "sensor_topic",
            "mqtt_topic",
            "variable",
            "valor",
        )
        if c in df.columns
    ]
    df = df[orden]

    renombres = {
        "timestamp": "Fecha y hora",
        "zona_topic": "Zona (tópico)",
        "sensor_topic": "Sensor (tópico)",
        "mqtt_topic": "Tópico MQTT",
        "variable": "Variable",
        "valor": "Valor",
    }
    df = df.rename(columns={k: v for k, v in renombres.items() if k in df.columns})

    cfg = {}
    if "Zona (tópico)" in df.columns:
        cfg["Zona (tópico)"] = st.column_config.TextColumn(width="small")
    if "Sensor (tópico)" in df.columns:
        cfg["Sensor (tópico)"] = st.column_config.TextColumn(width="small")
    if "Tópico MQTT" in df.columns:
        cfg["Tópico MQTT"] = st.column_config.TextColumn(width="medium")
    if "Fecha y hora" in df.columns:
        cfg["Fecha y hora"] = st.column_config.TextColumn(width="small")
    if "Variable" in df.columns:
        cfg["Variable"] = st.column_config.TextColumn(width="medium")
    if "Valor" in df.columns:
        cfg["Valor"] = st.column_config.TextColumn(width="small")

    st.dataframe(df, use_container_width=True, column_config=cfg or None, hide_index=True)


def _grafico_tendencia(nombre: str, puntos: list) -> None:
    if not puntos:
        st.caption(f"«{nombre}»: sin puntos")
        return
    df = pd.DataFrame(puntos)
    df["t"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["v"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["t", "v"])
    if df.empty:
        st.caption(f"«{nombre}»: sin valores numéricos")
        return
    fig = px.line(
        df,
        x="t",
        y="v",
        markers=True,
        labels={"t": "Tiempo", "v": nombre},
    )
    fig.update_layout(
        title=dict(text=nombre, font=dict(size=14)),
        height=280,
        margin=dict(l=8, r=8, t=36, b=8),
        showlegend=False,
        template="plotly_white",
        xaxis_title=None,
        yaxis_title=None,
    )
    fig.update_traces(line=dict(width=2), marker=dict(size=5))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True})


variables_opciones = _fetch_variables()

# --- Tabla primero ---
st.subheader("Tabla — últimas lecturas")

opciones_select = ["Todas"] + variables_opciones

col_sel, col_btn = st.columns([3, 1])
with col_sel:
    variable_elegida = st.selectbox(
        "Variable a observar",
        options=opciones_select,
        index=0,
        help="Con una variable concreta se muestran las últimas 20 lecturas que incluyen ese campo. "
        "«Todas» muestra todas las mediciones de las últimas 20 lecturas en general.",
    )
with col_btn:
    st.write("")
    st.write("")
    if st.button("Actualizar datos", help="Vuelve a pedir variables y lecturas al servidor"):
        st.rerun()

params = {}
if variable_elegida != "Todas":
    params["variable"] = variable_elegida

data, err = _fetch_json_list(f"{API_BASE}/logs", params=params or None)

if err:
    st.error(f"No se pudo cargar las lecturas: {err}")
elif not data:
    if variable_elegida != "Todas":
        st.info(
            f"No hay lecturas recientes con el campo «{variable_elegida}». "
            "Probá otra variable o «Actualizar datos»."
        )
    else:
        st.info("Aún no hay lecturas registradas. Esperá unos segundos o probá «Actualizar datos».")
else:
    if variable_elegida == "Todas":
        filas = _lecturas_a_formato_largo(data)
    else:
        filas = _docs_a_filas_una_variable(data, variable_elegida)
    _mostrar_tabla(filas)

st.divider()

# --- Tendencias (2 columnas, 30 puntos fijos) ---
st.subheader("Tendencias en el tiempo")
st.caption(
    f"Elegí las variables a graficar. Cada gráfico usa los últimos **{PUNTOS_SERIE}** puntos por variable; grilla de **{COLUMNAS_TENDENCIA}** columnas."
)

if not variables_opciones:
    st.warning("No hay variables detectadas todavía. Revisá que el backend y MongoDB tengan datos.")
else:
    default_sel = variables_opciones[: min(4, len(variables_opciones))]
    vars_tendencia = st.multiselect(
        "Variables a graficar",
        options=variables_opciones,
        default=default_sel,
        help="Máximo 16 variables por pedido al servidor.",
    )

    if vars_tendencia:
        series_data, s_err = _fetch_series(vars_tendencia, PUNTOS_SERIE)
        if s_err:
            st.error(f"No se pudieron cargar las series: {s_err}")
        elif series_data is not None:
            for i in range(0, len(vars_tendencia), COLUMNAS_TENDENCIA):
                row = st.columns(COLUMNAS_TENDENCIA)
                for j, var in enumerate(vars_tendencia[i : i + COLUMNAS_TENDENCIA]):
                    with row[j]:
                        _grafico_tendencia(var, series_data.get(var, []))
