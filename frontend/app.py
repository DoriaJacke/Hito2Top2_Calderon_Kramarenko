import math
import os
import streamlit as st
import requests
import pandas as pd

API_BASE = os.getenv("REST_API_URL", "http://rest_api:5000")

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
    """Devuelve (lista, None) o (None, mensaje_error)."""
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


variables_opciones = _fetch_variables()
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
    st.write("")  # alinea con el select
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
