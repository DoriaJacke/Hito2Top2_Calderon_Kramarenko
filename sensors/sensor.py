import paho.mqtt.client as mqtt
import time, random, os, json, ssl

sensor_id        = os.getenv("SENSOR_ID", "0")
AWS_ENDPOINT     = os.getenv("AWS_IOT_ENDPOINT", "a2apsmaa0mdv52-ats.iot.us-east-1.amazonaws.com")
AWS_PORT         = 8883
CERT_DIR         = os.getenv("CERT_DIR", "/app/certs")
TOPIC            = "campo/sensores"

client = mqtt.Client(client_id=f"sensor_{sensor_id}", protocol=mqtt.MQTTv311)
client.tls_set(
    ca_certs=f"{CERT_DIR}/AmazonRootCA1.pem",
    certfile=f"{CERT_DIR}/certificate.pem.crt",
    keyfile=f"{CERT_DIR}/private.pem.key",
    tls_version=ssl.PROTOCOL_TLSv1_2
)

client.connect(AWS_ENDPOINT, AWS_PORT, keepalive=60)
client.loop_start()

print(f"[Sensor {sensor_id}] Conectado a AWS IoT Core: {AWS_ENDPOINT}")

while True:
    data = {
        "sensor_id": sensor_id,
        "temperatura": round(random.uniform(10, 35), 2),
        "humedad":     round(random.uniform(30, 90), 2)
    }

    if random.random() > 0.2:
        client.publish(TOPIC, json.dumps(data), qos=1)
        print(f"[Sensor {sensor_id}] Enviado: {data}")
    else:
        print(f"[Sensor {sensor_id}] Fallo de red simulado — mensaje no enviado")

    time.sleep(3)
