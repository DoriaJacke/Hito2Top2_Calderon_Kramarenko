import paho.mqtt.client as mqtt
import json, time, os, ssl
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

AWS_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT", "a2apsmaa0mdv52-ats.iot.us-east-1.amazonaws.com")
AWS_PORT     = 8883
CERT_DIR     = os.getenv("CERT_DIR", "/app/certs")
TOPIC        = "campo/sensores"

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
        client.subscribe(TOPIC, qos=1)
        print(f"Suscrito al topic: {TOPIC}")
    else:
        print(f"Error al conectar, código: {rc}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        coleccion.insert_one(data)
        print(f"Guardado en MongoDB: {data}")
    except Exception as e:
        print(f"Error procesando mensaje: {e}")

client = mqtt.Client(client_id="subscriber_agro", protocol=mqtt.MQTTv311)
client.tls_set(
    ca_certs=f"{CERT_DIR}/AmazonRootCA1.pem",
    certfile=f"{CERT_DIR}/certificate.pem.crt",
    keyfile=f"{CERT_DIR}/private.pem.key",
    tls_version=ssl.PROTOCOL_TLSv1_2
)
client.on_connect = on_connect
client.on_message = on_message

client.connect(AWS_ENDPOINT, AWS_PORT, keepalive=60)
client.loop_forever()
