import json
import os
import ssl
import time

import paho.mqtt.client as mqtt
from prometheus_client import Counter, Histogram, start_http_server
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

AWS_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT", "a2apsmaa0mdv52-ats.iot.us-east-1.amazonaws.com")
AWS_PORT = 8883
CERT_DIR = os.getenv("CERT_DIR", "/app/certs")
MQTT_ZONE = os.getenv("MQTT_ZONE", "zona_sur_calderon_kramarenko")
TOPIC_SUBSCRIBE = os.getenv("MQTT_TOPIC_SUBSCRIBE", f"mina/{MQTT_ZONE}/#")
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))

ca_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_CA_FILE", "AmazonRootCA1.pem"))
cert_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_CERT_FILE", "certificate.pem.crt"))
key_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_KEY_FILE", "private.pem.key"))

# --- Prometheus (observabilidad Hito 2) ---
IOT_MQTT_LATENCY = Histogram(
    "iot_mqtt_publish_to_subscribe_latency_seconds",
    "Latencia desde published_ts_ms en el publicador hasta recepción en el suscriptor (s).",
    ["zona"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.25, 0.5, 0.75, 1.0, 2.0, 5.0, 10.0, 30.0),
)
IOT_MQTT_MESSAGES = Counter(
    "iot_mqtt_messages_received_total",
    "Mensajes MQTT recibidos por el suscriptor (proxy de frecuencia de publicación por zona).",
    ["zona"],
)
IOT_MQTT_PAYLOAD_BYTES = Counter(
    "iot_mqtt_subscriber_payload_bytes_total",
    "Bytes de payload MQTT recibidos en el suscriptor (volumen de red entrante aprox.).",
    ["zona"],
)
IOT_MONGODB_INSERT_BYTES = Counter(
    "iot_mongodb_lecturas_insert_bytes_total",
    "Suma estimada en bytes de documentos insertados en agro_iot.lecturas (JSON serializado).",
)


def conectar_mongo(reintentos=10, espera=3):
    for intento in range(1, reintentos + 1):
        try:
            cliente = MongoClient("mongodb://mongodb:27017/", serverSelectionTimeoutMS=3000)
            cliente.admin.command("ping")
            print("Conectado a MongoDB")
            return cliente
        except ConnectionFailure:
            print(f"MongoDB no disponible, reintento {intento}/{reintentos}...")
            time.sleep(espera)
    raise RuntimeError("No se pudo conectar a MongoDB tras varios intentos")


def _iniciar_metricas():
    start_http_server(METRICS_PORT)
    print(f"Prometheus metrics en http://0.0.0.0:{METRICS_PORT}/metrics")


mongo = conectar_mongo()
coleccion = mongo["agro_iot"]["lecturas"]

_iniciar_metricas()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Subscriber conectado a AWS IoT Core: {AWS_ENDPOINT}")
        client.subscribe(TOPIC_SUBSCRIBE, qos=1)
        print(f"Suscrito al topic: {TOPIC_SUBSCRIBE}")
    else:
        print(f"Error al conectar, código: {rc}")


def on_message(client, userdata, msg):
    zona_metrica = MQTT_ZONE
    payload_len = len(msg.payload)
    try:
        data = json.loads(msg.payload.decode())
        zona_metrica = data.get("zona") or MQTT_ZONE

        pub_ms = data.get("published_ts_ms")
        if pub_ms is not None:
            try:
                lat_s = (time.time() * 1000.0 - float(pub_ms)) / 1000.0
                if 0 <= lat_s < 120:
                    IOT_MQTT_LATENCY.labels(zona=zona_metrica).observe(lat_s)
            except (TypeError, ValueError):
                pass

        IOT_MQTT_MESSAGES.labels(zona=zona_metrica).inc()
        IOT_MQTT_PAYLOAD_BYTES.labels(zona=zona_metrica).inc(payload_len)

        data.pop("published_ts_ms", None)
        data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        data["mqtt_topic"] = msg.topic
        partes = msg.topic.strip("/").split("/")
        if len(partes) >= 3 and partes[0] == "mina":
            data["zona_topic"] = partes[1]
            data["sensor_topic"] = partes[2]

        insert_bytes = len(json.dumps(data, default=str).encode("utf-8"))
        coleccion.insert_one(data)
        IOT_MONGODB_INSERT_BYTES.inc(insert_bytes)
        print(f"Guardado en MongoDB: {data}")
    except Exception as e:
        print(f"Error procesando mensaje: {e}")


client = mqtt.Client(client_id="subscriber_agro", protocol=mqtt.MQTTv311)
client.tls_set(
    ca_certs=ca_path,
    certfile=cert_path,
    keyfile=key_path,
    tls_version=ssl.PROTOCOL_TLSv1_2,
)
client.on_connect = on_connect
client.on_message = on_message

client.connect(AWS_ENDPOINT, AWS_PORT, keepalive=60)
client.loop_forever()
