import paho.mqtt.client as mqtt
import json, time, os, ssl
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

AWS_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT", "a2apsmaa0mdv52-ats.iot.us-east-1.amazonaws.com")
AWS_PORT     = 8883
CERT_DIR     = os.getenv("CERT_DIR", "/app/certs")
# Wildcard: todos los sensores bajo sensor/<zona>/...
MQTT_ZONE       = os.getenv("MQTT_ZONE", "zona_sur_calderon_kramarenko")
TOPIC_SUBSCRIBE = os.getenv("MQTT_TOPIC_SUBSCRIBE", f"sensor/{MQTT_ZONE}/#")

ca_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_CA_FILE", "AmazonRootCA1.pem"))
cert_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_CERT_FILE", "certificate.pem.crt"))
key_path = os.path.join(CERT_DIR, os.getenv("AWS_IOT_KEY_FILE", "private.pem.key"))

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

mongo     = conectar_mongo()
coleccion = mongo["agro_iot"]["lecturas"]

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Subscriber conectado a AWS IoT Core: {AWS_ENDPOINT}")
        client.subscribe(TOPIC_SUBSCRIBE, qos=1)
        print(f"Suscrito al topic: {TOPIC_SUBSCRIBE}")
    else:
        print(f"Error al conectar, código: {rc}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        data["mqtt_topic"] = msg.topic
        partes = msg.topic.strip("/").split("/")
        if len(partes) >= 3 and partes[0] == "sensor":
            data["zona_topic"] = partes[1]
            data["sensor_topic"] = partes[2]
        coleccion.insert_one(data)
        print(f"Guardado en MongoDB: {data}")
    except Exception as e:
        print(f"Error procesando mensaje: {e}")

client = mqtt.Client(client_id="subscriber_agro", protocol=mqtt.MQTTv311)
client.tls_set(
    ca_certs=ca_path,
    certfile=cert_path,
    keyfile=key_path,
    tls_version=ssl.PROTOCOL_TLSv1_2
)
client.on_connect = on_connect
client.on_message = on_message

client.connect(AWS_ENDPOINT, AWS_PORT, keepalive=60)
client.loop_forever()
