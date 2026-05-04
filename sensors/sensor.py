import paho.mqtt.client as mqtt
import json
import os
import random
import ssl
import time

# Zona fija del grupo (prioridad #1 — convención de tópicos)
MQTT_ZONE = os.getenv("MQTT_ZONE", "zona_sur_calderon_kramarenko")
# Último segmento del topic: mina/<zona>/<SENSOR_NAME>
SENSOR_NAME = os.getenv("SENSOR_NAME", os.getenv("SENSOR_ID", "sensor_generico"))

AWS_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT", "a2apsmaa0mdv52-ats.iot.us-east-1.amazonaws.com")
AWS_PORT = 8883
CERT_DIR = os.getenv("CERT_DIR", "/app/certs")
TOPIC = f"mina/{MQTT_ZONE}/{SENSOR_NAME}"

ca_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_CA_FILE", "AmazonRootCA1.pem"))
cert_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_CERT_FILE", "certificate.pem.crt"))
key_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_KEY_FILE", "private.pem.key"))


def lectura_por_sensor(nombre: str) -> dict:
    """Simula la lectura principal según el nombre del sensor (mina — Hito 2)."""
    n = nombre.lower()
    if n == "temperatura_ambiente":
        return {"temperatura_c": round(random.uniform(10, 35), 2)}
    if n == "humedad_relativa":
        return {"humedad_pct": round(random.uniform(30, 90), 2)}
    if n == "vibracion":
        return {"vibracion_ms2": round(random.uniform(0.01, 2.5), 3)}
    if n == "toneladas_hora":
        return {"toneladas_por_hora": round(random.uniform(50, 220), 2)}
    if n == "ciclos_completados":
        return {"ciclos_completados": random.randint(0, 120)}
    if n == "ph":
        return {"ph": round(random.uniform(5.5, 8.5), 2)}
    if n == "co2":
        return {"co2_ppm": round(random.uniform(400, 1200), 1)}
    if n == "so2":
        return {"so2_ppm": round(random.uniform(0, 50), 2)}
    if n == "material_particulado":
        return {"material_particulado_ug_m3": round(random.uniform(10, 180), 1)}
    # genérico / nombre desconocido
    return {
        "temperatura_c": round(random.uniform(10, 35), 2),
        "humedad_pct": round(random.uniform(30, 90), 2),
    }


client = mqtt.Client(client_id=f"pub_{MQTT_ZONE}_{SENSOR_NAME}"[:64], protocol=mqtt.MQTTv311)
client.tls_set(
    ca_certs=ca_path,
    certfile=cert_path,
    keyfile=key_path,
    tls_version=ssl.PROTOCOL_TLSv1_2,
)

client.connect(AWS_ENDPOINT, AWS_PORT, keepalive=60)
client.loop_start()

print(f"[{SENSOR_NAME}] Conectado a AWS IoT Core: {AWS_ENDPOINT}")
print(f"[{SENSOR_NAME}] Publicando en: {TOPIC}")

while True:
    mediciones = lectura_por_sensor(SENSOR_NAME)
    data = {
        "zona": MQTT_ZONE,
        "sensor": SENSOR_NAME,
        **mediciones,
    }

    if random.random() > 0.2:
        client.publish(TOPIC, json.dumps(data), qos=1)
        print(f"[{SENSOR_NAME}] Enviado: {data}")
    else:
        print(f"[{SENSOR_NAME}] Fallo de red simulado — mensaje no enviado")

    time.sleep(3)
