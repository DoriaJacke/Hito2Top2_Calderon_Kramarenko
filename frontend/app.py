import streamlit as st
import requests
import pandas as pd

st.title("Monitoreo minero — Zona Sur Calderón Kramarenko")
st.caption("Últimas 20 lecturas MQTT (sensor/zona_sur_calderon_kramarenko/…) en MongoDB")

if st.button("Actualizar"):
    try:
        res = requests.get("http://rest_api:5000/logs")
        data = res.json()

        if not data:
            st.info("Aún no hay lecturas registradas. Esperá unos segundos y volvé a actualizar.")
        else:
            df = pd.DataFrame(data)
            prefer = [
                "timestamp",
                "zona",
                "sensor",
                "mqtt_topic",
                "zona_topic",
                "sensor_topic",
            ]
            rest = sorted(c for c in df.columns if c not in prefer and c != "_id")
            cols = [c for c in prefer if c in df.columns] + rest
            df = df[[c for c in cols if c in df.columns]]
            st.dataframe(df, use_container_width=True)

    except Exception as e:
        st.error(f"No se pudo conectar al backend: {e}")
