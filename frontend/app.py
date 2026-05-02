import streamlit as st
import requests
import pandas as pd

st.title("Monitoreo Agrónomo IoT")
st.caption("Últimas 20 lecturas registradas en MongoDB")

if st.button("Actualizar"):
    try:
        res = requests.get("http://rest_api:5000/logs")
        data = res.json()

        if not data:
            st.info("Aún no hay lecturas registradas. Esperá unos segundos y volvé a actualizar.")
        else:
            df = pd.DataFrame(data)
            col_orden = ["timestamp", "sensor_id", "temperatura", "humedad"]
            df = df[[c for c in col_orden if c in df.columns]]
            st.dataframe(df, use_container_width=True)

    except Exception as e:
        st.error(f"No se pudo conectar al backend: {e}")
