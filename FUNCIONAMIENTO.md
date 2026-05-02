# Documento Técnico: Funcionamiento del Sistema IoT Agrícola

## Índice

1. [Visión general del sistema](#1-visión-general-del-sistema)
2. [Arquitectura y flujo de datos](#2-arquitectura-y-flujo-de-datos)
3. [Tecnologías utilizadas: MQTT y REST API](#3-tecnologías-utilizadas-mqtt-y-rest-api)
4. [Diferencias fundamentales entre MQTT y REST](#4-diferencias-fundamentales-entre-mqtt-y-rest)
5. [Componentes del sistema en detalle](#5-componentes-del-sistema-en-detalle)
6. [MongoDB como capa de persistencia](#6-mongodb-como-capa-de-persistencia)
7. [QoS, Client ID y mecanismos internos de MQTT](#7-qos-client-id-y-mecanismos-internos-de-mqtt)
8. [Por qué se usa MQTT para los sensores y REST para el frontend](#8-por-qué-se-usa-mqtt-para-los-sensores-y-rest-para-el-frontend)
9. [Ciclo de vida completo de un dato](#9-ciclo-de-vida-completo-de-un-dato)

---

## 1. Visión general del sistema

Este proyecto simula una red de sensores agrícolas que monitorean **temperatura** y **humedad** en campo. El sistema está dividido en dos capas de comunicación bien diferenciadas:

- **Capa de telemetría (MQTT):** los sensores publican datos en tiempo real hacia un broker central. Es liviana, eficiente y tolerante a conexiones intermitentes — ideal para dispositivos IoT embebidos.
- **Capa de consulta (REST API):** el dashboard web consulta los datos almacenados bajo demanda. Es el protocolo estándar de la web, apropiado para interfaces de usuario que necesitan hacer preguntas puntuales.

La combinación de ambas tecnologías no es casual: cada una resuelve un problema distinto dentro del mismo sistema.

```
CAPA IoT (MQTT)                        CAPA WEB (REST + HTTP)
─────────────────────────────────      ─────────────────────────────────
[sensor1] ──┐                          [Frontend Streamlit :8501]
            ├──► [Broker MQTT]               │
[sensor2] ──┘       │                        │ GET /logs (HTTP)
                    ▼                        ▼
              [subscriber]            [REST API Flask :5000]
                    │                        │
                    └──► [MongoDB :27017] ◄──┘
                          agro_iot.lecturas
```

---

## 2. Arquitectura y flujo de datos

El sistema tiene **7 contenedores Docker** que se comunican entre sí:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                           │
│                                                                 │
│  ┌──────────┐   publish    ┌────────────────┐   subscribe       │
│  │ sensor1  │─────────────►│ Eclipse        │◄─────────────┐    │
│  └──────────┘  topic:      │ Mosquitto      │  topic:      │    │
│                campo/      │ (broker MQTT)  │  campo/      │    │
│  ┌──────────┐  sensores    │ :1883          │  sensores    │    │
│  │ sensor2  │─────────────►│                │          ┌───┴──┐ │
│  └──────────┘              └────────────────┘          │ sub- │ │
│                                                        │scrib.│ │
│                                                        └───┬──┘ │
│                                  ┌──────────────────┐      │    │
│  ┌──────────────────┐  GET /logs │  REST API Flask  │      │    │
│  │ Frontend         │───────────►│  :5000           │      │    │
│  │ Streamlit :8501  │◄───────────│                  │      │    │
│  └──────────────────┘  JSON []   └────────┬─────────┘      │    │
│                                           │  insert/find   │    │
│                                           ▼                ▼    │
│                                  ┌──────────────────────────┐   │
│                                  │  MongoDB :27017          │   │
│                                  │  db: agro_iot            │   │
│                                  │  colección: lecturas     │   │
│                                  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Orden de arranque

1. **Mosquitto** levanta primero y queda escuchando en el puerto 1883.
2. **MongoDB** levanta y queda disponible en el puerto 27017.
3. **subscriber** se conecta al broker y a MongoDB, y queda en espera de mensajes.
4. **sensor1** y **sensor2** se conectan al broker y comienzan a publicar datos cada 3 segundos.
5. **rest_api** arranca Flask, conecta a MongoDB y expone el endpoint `/logs`.
6. **frontend** arranca Streamlit y espera que el usuario presione el botón.

---

## 3. Tecnologías utilizadas: MQTT y REST

### 3.1 MQTT (Message Queuing Telemetry Transport)

MQTT es un protocolo de mensajería **publicar/suscribir** (pub/sub) diseñado para dispositivos con recursos limitados y redes de baja confiabilidad.

**Elementos clave:**


| Concepto       | Rol en este proyecto                                                     |
| -------------- | ------------------------------------------------------------------------ |
| **Broker**     | Eclipse Mosquitto — el servidor central que recibe y distribuye mensajes |
| **Publisher**  | `sensor1` y `sensor2` — publican datos de campo                          |
| **Subscriber** | `subscriber` — escucha y persiste los mensajes                           |
| **Topic**      | `campo/sensores` — el "canal" por el que fluye la información            |
| **Payload**    | JSON con `sensor_id`, `temperatura`, `humedad`                           |


**Cómo funciona en el código (`sensor.py`):**

```python
client = mqtt.Client()
client.connect("mqtt", 1883, 60)     # Conexión al broker
client.publish("campo/sensores", json.dumps(data))  # Publicación
```

El sensor no sabe quién recibirá el mensaje. Solo lo entrega al broker y continúa. Esto se llama **desacoplamiento**: el emisor y el receptor no se conocen entre sí.

**Cómo funciona en el código (`subscriber.py`):**

```python
client = mqtt.Client()
client.on_message = on_message       # Callback al recibir mensaje
client.connect("mqtt", 1883, 60)
client.subscribe("campo/sensores")   # Suscripción al topic
client.loop_forever()                # Bucle de escucha indefinido
```

El suscriptor declara interés en el topic y el broker le entrega cada mensaje que llegue. `loop_forever()` mantiene la conexión activa de forma bloqueante.

**Qué ocurre cuando llega un mensaje:**

```python
def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())          # Decodifica JSON
    log = f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {data}\n"
    with open("/app/shared/logs.txt", "a") as f:     # Persiste en disco
        f.write(log)
```

---

### 3.2 REST API (Representational State Transfer)

REST es un estilo de arquitectura para sistemas distribuidos basado en HTTP. Cada recurso tiene una URL y se accede mediante verbos estándar (`GET`, `POST`, `PUT`, `DELETE`).

**Características en este proyecto:**


| Aspecto   | Detalle                                     |
| --------- | ------------------------------------------- |
| Framework | Flask (Python)                              |
| Puerto    | 5000                                        |
| Endpoint  | `GET /logs`                                 |
| Respuesta | Array JSON con las últimas 20 líneas de log |
| Modelo    | Petición → Respuesta (bajo demanda)         |


**Cómo funciona en el código (`rest_api/app.py`):**

```python
@app.route("/logs", methods=["GET"])
def logs():
    with open("/app/shared/logs.txt", "r") as f:
        data = f.readlines()
    return jsonify(data[-20:])      # Devuelve las últimas 20 entradas
```

El endpoint es **stateless**: cada vez que el cliente hace `GET /logs` recibe una respuesta independiente. El servidor no recuerda peticiones anteriores.

**Cómo lo consume el frontend (`frontend/app.py`):**

```python
res = requests.get("http://rest_api:5000/logs")  # Petición HTTP
data = res.json()                                 # Parsea respuesta JSON
for line in data:
    st.text(line)                                 # Muestra en pantalla
```

---

## 4. Diferencias fundamentales entre MQTT y REST

Esta es la comparación más importante para entender por qué el proyecto usa ambos protocolos:


| Característica                   | MQTT                                         | REST / HTTP                                   |
| -------------------------------- | -------------------------------------------- | --------------------------------------------- |
| **Modelo de comunicación**       | Publicar / Suscribir (asíncrono)             | Petición / Respuesta (síncrono)               |
| **Quién inicia la comunicación** | El publisher envía cuando tiene datos        | El cliente pregunta cuando necesita datos     |
| **Conexión**                     | Persistente (el cliente permanece conectado) | Sin estado (una conexión por petición)        |
| **Dirección del mensaje**        | Uno a muchos (un publisher → N suscriptores) | Uno a uno (cliente → servidor)                |
| **Protocolo base**               | TCP (propio, puerto 1883)                    | HTTP (puerto 80/443/5000)                     |
| **Overhead**                     | Muy bajo (cabeceras de 2 bytes mínimo)       | Más alto (cabeceras HTTP completas)           |
| **Ideal para**                   | Sensores IoT, telemetría, tiempo real        | APIs web, dashboards, integraciones           |
| **Manejo de desconexión**        | Tiene mecanismos integrados (QoS, will)      | Sin manejo especial                           |
| **Rol en este proyecto**         | Transporte de datos del sensor al suscriptor | Consulta de datos almacenados por el frontend |


### Diagrama de modelo de comunicación

```
MQTT: Publicar / Suscribir
──────────────────────────────────────────────────────
  sensor1 ──► [broker] ──► subscriber
  sensor2 ──►           ──► (cualquier otro suscriptor)
  
  El broker distribuye a TODOS los que se hayan suscrito.
  El publisher no sabe quién recibe el mensaje.


REST: Petición / Respuesta
──────────────────────────────────────────────────────
  frontend ──GET /logs──► rest_api
           ◄──JSON []───
  
  El cliente pregunta. El servidor responde. Se termina.
  No hay conexión persistente.
```

### ¿Por qué MQTT en los sensores y no REST?

Un sensor en campo podría tener conectividad intermitente, batería limitada y necesita enviar datos constantemente aunque nadie esté escuchando. MQTT fue diseñado exactamente para eso:

- No necesita que el receptor esté disponible al momento del envío.
- El overhead de protocolo es mínimo (importante en redes 2G/3G o LoRa).
- Múltiples consumidores pueden escuchar el mismo topic sin modificar el sensor.

Si se usara REST en los sensores, cada sensor tendría que hacer un `POST` HTTP al servidor, lo que implica:

- Conocer la dirección del servidor de destino.
- Esperar una respuesta antes de continuar.
- Más consumo de ancho de banda y batería.

### ¿Por qué REST en el frontend y no MQTT?

El frontend es un dashboard web que solo necesita datos **cuando el usuario presiona un botón**. REST es perfecto para esto:

- La consulta es puntual y bajo demanda.
- El navegador/Streamlit habla HTTP nativamente.
- No tiene sentido mantener una conexión MQTT abierta si el usuario solo consulta esporádicamente.

---

## 5. Componentes del sistema en detalle

### 5.1 Broker MQTT — Eclipse Mosquitto

```yaml
# docker-compose.yml
mqtt:
  image: eclipse-mosquitto
  ports:
    - "1883:1883"
  volumes:
    - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
```

```
# mosquitto.conf
listener 1883
allow_anonymous true
```

Mosquitto es el núcleo de la capa MQTT. Actúa como intermediario: recibe publicaciones y las redistribuye a los suscriptores registrados. La configuración `allow_anonymous true` es necesaria porque los clientes no tienen credenciales (válido en entorno de laboratorio).

---

### 5.2 Sensores — `sensor.py`

```python
sensor_id = os.getenv("SENSOR_ID", "0")    # Identificación desde variable de entorno
client = mqtt.Client()
client.connect("mqtt", 1883, 60)

while True:
    data = {
        "sensor_id": sensor_id,
        "temperatura": round(random.uniform(10, 35), 2),
        "humedad": round(random.uniform(30, 90), 2)
    }
    if random.random() > 0.2:               # 80% de probabilidad de envío
        client.publish("campo/sensores", json.dumps(data))
    else:
        print(f"[Sensor {sensor_id}] Fallo de red simulado — mensaje no enviado")
    time.sleep(3)
```

**Puntos clave:**

- `SENSOR_ID` se inyecta como variable de entorno desde `docker-compose.yml`, lo que permite reusar la misma imagen para múltiples instancias (`sensor1`, `sensor2`).
- La probabilidad del 20% de "fallo de red" simula condiciones reales de campo donde la conectividad no siempre es estable.
- El payload es JSON, formato universal que el suscriptor puede parsear fácilmente.

**Ejemplo de mensaje publicado:**

```json
{"sensor_id": "1", "temperatura": 22.45, "humedad": 67.83}
```

---

### 5.3 Suscriptor MQTT — `subscriber.py`

```python
LOG_FILE = "/app/shared/logs.txt"

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    log = f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {data}\n"
    with open(LOG_FILE, "a") as f:
        f.write(log)

client = mqtt.Client()
client.on_message = on_message          # Registra el callback
client.connect("mqtt", 1883, 60)
client.subscribe("campo/sensores")
client.loop_forever()                   # Bloquea e itera el loop de red
```

**Puntos clave:**

- `on_message` es un **callback**: se ejecuta automáticamente cada vez que llega un mensaje al topic suscrito. El suscriptor no hace polling; el broker lo notifica.
- `loop_forever()` mantiene la conexión viva y despacha los callbacks en el hilo principal.
- El archivo se abre en modo `"a"` (append) para acumular registros sin sobreescribir.

**Ejemplo de línea escrita en `logs.txt`:**

```
2024-06-01 12:00:03 - {'sensor_id': '1', 'temperatura': 22.45, 'humedad': 67.83}
```

---

### 5.4 REST API — `rest_api/app.py`

```python
from flask import Flask, jsonify

app = Flask(__name__)
LOG_FILE = "/app/shared/logs.txt"

@app.route("/logs", methods=["GET"])
def logs():
    try:
        with open(LOG_FILE, "r") as f:
            data = f.readlines()
        return jsonify(data[-20:])           # Últimas 20 líneas
    except FileNotFoundError:
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

**Puntos clave:**

- La API es **stateless**: no guarda ningún estado entre peticiones. Cada `GET /logs` lee el archivo en ese momento y devuelve lo que haya.
- `data[-20:]` limita la respuesta a las últimas 20 líneas para evitar transferencias innecesariamente grandes.
- El manejo de excepciones diferenciado (`FileNotFoundError` vs `Exception`) permite devolver respuestas coherentes: lista vacía si aún no hay datos, error 500 con detalle si falla algo inesperado.
- `host="0.0.0.0"` es necesario para que Flask sea accesible desde otros contenedores Docker.

**Respuesta HTTP típica:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

[
  "2024-06-01 12:00:03 - {'sensor_id': '1', 'temperatura': 22.45, 'humedad': 67.83}\n",
  "2024-06-01 12:00:06 - {'sensor_id': '2', 'temperatura': 18.10, 'humedad': 72.00}\n"
]
```

---

### 5.5 Frontend — `frontend/app.py`

```python
import streamlit as st
import requests

st.title("Monitoreo Agrónomo IoT")

if st.button("Actualizar"):
    try:
        res = requests.get("http://rest_api:5000/logs")
        data = res.json()
        for line in data:
            st.text(line)
    except Exception as e:
        st.error(f"No se pudo conectar al backend: {e}")
```

**Puntos clave:**

- La URL `http://rest_api:5000` funciona porque Docker resuelve el nombre del servicio (`rest_api`) a la IP del contenedor correspondiente dentro de la red interna.
- Streamlit corre en el **servidor**, no en el navegador del usuario. El `requests.get` es una llamada servidor-a-servidor dentro de Docker, no una llamada del navegador.
- La interacción es **pull**: el usuario decide cuándo actualizar los datos. No hay actualización automática.

---

## 6. MongoDB como capa de persistencia

MongoDB reemplaza al archivo de texto como almacenamiento central. Es el puente entre la capa MQTT (escritura) y la capa REST (lectura), y elimina la necesidad de un volumen Docker compartido.

### Estructura en MongoDB

```
Base de datos: agro_iot
└── Colección: lecturas
    ├── { sensor_id: "1", temperatura: 22.45, humedad: 67.83, timestamp: "2024-06-01 12:00:03" }
    ├── { sensor_id: "2", temperatura: 18.10, humedad: 72.00, timestamp: "2024-06-01 12:00:06" }
    └── ...
```

Cada documento es una lectura de un sensor. MongoDB asigna automáticamente un `_id` único a cada documento (que la API excluye de la respuesta con `{"_id": 0}`).

### Cómo escribe el subscriber

```python
mongo = MongoClient("mongodb://mongodb:27017/")
coleccion = mongo["agro_iot"]["lecturas"]

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    coleccion.insert_one(data)         # Inserta un documento por cada mensaje MQTT
```

### Cómo lee la REST API

```python
docs = list(
    coleccion.find({}, {"_id": 0})     # Excluye el campo _id interno de Mongo
             .sort("timestamp", DESCENDING)
             .limit(20)                # Últimas 20 lecturas
)
return jsonify(docs)
```

### Lógica de reconexión

Ambos servicios (`subscriber` y `rest_api`) incluyen un bucle de reintentos al iniciar, porque MongoDB puede tardar unos segundos en estar disponible:

```python
def conectar_mongo(reintentos=10, espera=3):
    for intento in range(1, reintentos + 1):
        try:
            cliente = MongoClient("mongodb://mongodb:27017/", serverSelectionTimeoutMS=3000)
            cliente.admin.command("ping")   # Verifica que el servidor responde
            return cliente
        except ConnectionFailure:
            time.sleep(espera)
```

Además, `restart: on-failure` en `docker-compose.yml` hace que Docker reinicie el contenedor si falla durante el arranque.

### Ventajas sobre el archivo de texto


| Aspecto       | Archivo de texto (`logs.txt`)       | MongoDB                                  |
| ------------- | ----------------------------------- | ---------------------------------------- |
| Consultas     | Solo lectura secuencial             | Filtros, ordenamiento, índices           |
| Concurrencia  | Sin control de acceso simultáneo    | Manejo nativo de escrituras concurrentes |
| Escalabilidad | Crece sin límite estructurado       | Colecciones indexables y escalables      |
| Persistencia  | Volumen Docker compartido necesario | Volumen propio del contenedor `mongodb`  |
| Formato       | Texto plano (strings)               | Documentos JSON estructurados            |


---

## 7. QoS, Client ID y mecanismos internos de MQTT

Esta sección explica los conceptos internos del protocolo MQTT que determinan cómo se identifican los clientes ante el broker, con qué garantías se entregan los mensajes y qué otros mecanismos ofrece el protocolo para situaciones críticas.

---

### 7.1 Client ID — identificación ante el broker

Cada cliente MQTT (publisher o subscriber) debe presentarse al broker con un **Client ID** único. Es el equivalente a un nombre de usuario de sesión dentro del broker.

```
sensor1  ──connect(clientId="sensor1-abc")──►  [Mosquitto]
sensor2  ──connect(clientId="sensor2-xyz")──►  [Mosquitto]
subscriber──connect(clientId="sub-001")────►  [Mosquitto]
```

**En el código actual** (`sensor.py` y `subscriber.py`):

```python
client = mqtt.Client()   # Sin Client ID explícito
```

Cuando no se especifica un ID, la librería `paho-mqtt` genera uno **aleatorio** en cada conexión. Esto implica:

- Cada vez que el contenedor reinicia, el broker lo trata como un cliente nuevo.
- El broker no conserva ningún estado asociado a ese cliente entre reinicios.
- Es aceptable para este demo donde no se necesita persistencia de sesión.

**Cómo especificar un Client ID explícito** (mejor práctica):

```python
client = mqtt.Client(client_id="sensor-1", clean_session=True)
```

El parámetro `clean_session` define qué pasa con el estado del cliente cuando se desconecta:


| `clean_session`  | Comportamiento al reconectar                                                                                         |
| ---------------- | -------------------------------------------------------------------------------------------------------------------- |
| `True` (default) | El broker descarta toda la sesión anterior (suscripciones, mensajes pendientes)                                      |
| `False`          | El broker recuerda la sesión y entrega mensajes que llegaron mientras el cliente estuvo offline (requiere QoS 1 o 2) |


---

### 7.2 El handshake de conexión MQTT

Cuando un cliente se conecta al broker ocurre un intercambio de paquetes de control:

```
Cliente                          Broker (Mosquitto)
   │                                    │
   │──── CONNECT ──────────────────────►│
   │     clientId: "sensor-1"           │
   │     cleanSession: true             │
   │     keepAlive: 60 seg              │
   │                                    │
   │◄─── CONNACK ───────────────────────│
   │     returnCode: 0 (Accepted)       │
   │                                    │
   │  [conexión establecida]            │
   │                                    │
   │──── PUBLISH ──────────────────────►│  (sensor publica)
   │     topic: campo/sensores          │
   │     payload: {...}                 │
   │     QoS: 0                         │
   │                                    │
   │──── PINGREQ ──────────────────────►│  (keepAlive cada 60 seg)
   │◄─── PINGRESP ──────────────────────│
```

El parámetro `**keepAlive: 60**` que aparece en el código:

```python
client.connect("mqtt", 1883, 60)   # el tercer argumento es keepAlive en segundos
```

Le indica al broker que el cliente enviará un `PINGREQ` al menos cada 60 segundos para demostrar que sigue vivo. Si el broker no recibe ningún mensaje ni ping en ese lapso, considera al cliente desconectado.

---

### 7.3 QoS — Niveles de Calidad de Servicio

QoS (Quality of Service) es el mecanismo de MQTT para garantizar la entrega de mensajes. Define el contrato entre cliente y broker respecto a cuántas veces se intentará entregar cada mensaje.

Existen **tres niveles**:

---

#### QoS 0 — At most once (como máximo una vez)

```
Publisher                Broker               Subscriber
    │                      │                      │
    │──── PUBLISH ─────────►│                      │
    │     (sin ACK)         │──── PUBLISH ─────────►│
    │                       │     (sin ACK)         │
```

- El mensaje se envía **una sola vez**, sin confirmación.
- Si el broker o el suscriptor no están disponibles en ese momento, **el mensaje se pierde**.
- También llamado *"fire and forget"*.
- **Máxima velocidad, mínimo overhead**.

**En el proyecto actual**, todos los mensajes usan QoS 0 (valor por defecto):

```python
client.publish("campo/sensores", json.dumps(data))   # QoS=0 implícito
client.subscribe("campo/sensores")                    # QoS=0 implícito
```

Esto es razonable para datos de sensores de alta frecuencia: si se pierde una lectura de temperatura, la siguiente llega en 3 segundos.

---

#### QoS 1 — At least once (al menos una vez)

```
Publisher                Broker               Subscriber
    │                      │                      │
    │──── PUBLISH (id=1)───►│                      │
    │◄─── PUBACK (id=1) ────│                      │
    │                       │──── PUBLISH (id=1)───►│
    │                       │◄─── PUBACK (id=1) ────│
```

- El mensaje se envía y el broker **confirma la recepción** con un `PUBACK`.
- Si no llega el `PUBACK`, el publisher reenvía el mensaje.
- Garantiza que el mensaje llega **al menos una vez**, pero puede llegar **duplicado** si el `PUBACK` se pierde en el camino.
- El broker también confirma la entrega al suscriptor.

**Cuándo usarlo:** cuando perder un dato sería problemático (lectura de apertura de válvula, alarma de riego, etc.).

**Cómo activarlo en el proyecto:**

```python
# En el sensor (publisher):
client.publish("campo/sensores", json.dumps(data), qos=1)

# En el subscriber:
client.subscribe("campo/sensores", qos=1)
```

---

#### QoS 2 — Exactly once (exactamente una vez)

```
Publisher                Broker               Subscriber
    │                      │                      │
    │──── PUBLISH (id=1)───►│                      │
    │◄─── PUBREC (id=1) ────│                      │
    │──── PUBREL (id=1) ───►│                      │
    │◄─── PUBCOMP (id=1) ───│                      │
    │                       │──── PUBLISH (id=1)───►│
    │                       │◄─── PUBREC ───────────│
    │                       │──── PUBREL ───────────►│
    │                       │◄─── PUBCOMP ───────────│
```

- Protocolo de **4 pasos** (handshake doble) que garantiza entrega exactamente una vez.
- Sin duplicados, sin pérdidas.
- **Mayor overhead de red y CPU**.

**Cuándo usarlo:** transacciones críticas donde duplicar un comando sería peligroso (accionar una bomba de agua, enviar una orden de fertilización, etc.).

---

#### Comparativa de QoS


|                             | QoS 0                         | QoS 1             | QoS 2                            |
| --------------------------- | ----------------------------- | ----------------- | -------------------------------- |
| **Garantía**                | Como máximo 1 vez             | Al menos 1 vez    | Exactamente 1 vez                |
| **Paquetes intercambiados** | 1                             | 2                 | 4                                |
| **Posible pérdida**         | Sí                            | No                | No                               |
| **Posible duplicado**       | No                            | Sí                | No                               |
| **Overhead**                | Mínimo                        | Medio             | Alto                             |
| **Usado en el proyecto**    | ✓ (por defecto)               | —                 | —                                |
| **Caso de uso típico**      | Telemetría de alta frecuencia | Alertas, comandos | Facturación, actuadores críticos |


---

### 7.4 Topics y jerarquía

Un **topic** es una cadena de texto que actúa como canal de enrutamiento. El broker usa los topics para saber a quién entregar cada mensaje.

**En el proyecto:**

```
campo/sensores
```

Los topics se organizan en jerarquías separadas por `/`. Ejemplos de cómo podría expandirse:

```
campo/sensores            ← todos los sensores (lo que usa el proyecto)
campo/sensores/1          ← solo sensor 1
campo/sensores/2          ← solo sensor 2
campo/actuadores/riego    ← canal para comandos de riego
campo/alertas             ← canal para alarmas
```

**Wildcards para suscripciones:**


| Wildcard          | Símbolo | Ejemplo               | Coincide con                                             |
| ----------------- | ------- | --------------------- | -------------------------------------------------------- |
| Un nivel          | `+`     | `campo/+/temperatura` | `campo/sensor1/temperatura`, `campo/sensor2/temperatura` |
| Todos los niveles | `#`     | `campo/#`             | Todo lo que empiece con `campo/`                         |


```python
# Suscribirse a todos los sensores con wildcard:
client.subscribe("campo/sensores/+")   # sensor/1, sensor/2, etc.
client.subscribe("campo/#")            # todo lo del campo
```

---

### 7.5 Retained Messages — el último valor conocido

Un mensaje **retained** (retenido) es guardado por el broker y entregado **inmediatamente** a cualquier cliente que se suscriba al topic, incluso si el mensaje fue publicado antes de que ese cliente existiera.

```python
# Publicar con retain=True:
client.publish("campo/sensores/1", json.dumps(data), retain=True)
```

```
Flujo sin retain:
  sensor publica → broker entrega → subscriber recibe
  (si subscriber se conecta después, no recibe nada)

Flujo con retain:
  sensor publica (retain) → broker guarda último mensaje
  subscriber se conecta → broker entrega el último mensaje guardado inmediatamente
```

**Utilidad en IoT:** un nuevo dashboard que se conecta puede mostrar el último estado conocido de cada sensor sin esperar a que llegue la próxima publicación.

---

### 7.6 Last Will and Testament (LWT) — testamento del cliente

El **LWT** es un mensaje que el cliente registra en el broker durante la conexión. Si el cliente se desconecta de forma **inesperada** (sin enviar un `DISCONNECT` limpio), el broker publica ese mensaje automáticamente en el topic designado.

```python
client.will_set(
    topic="campo/estado/sensor1",
    payload='{"estado": "offline", "sensor_id": "1"}',
    qos=1,
    retain=True
)
client.connect("mqtt", 1883, 60)
```

```
Escenario normal:
  sensor se desconecta limpiamente → broker NO publica el LWT

Escenario de fallo (corte de luz, red caída, crash):
  broker detecta timeout de keepAlive → publica LWT automáticamente
  → subscriber recibe: {"estado": "offline", "sensor_id": "1"}
```

**En el proyecto actual no está implementado**, pero sería la forma correcta de detectar que un sensor de campo dejó de funcionar.

---

### 7.7 Estado de la sesión en el broker

El broker Mosquitto mantiene información de cada cliente conectado:

```
Cliente: sensor-1
├── Estado: CONECTADO
├── Client ID: sensor-1
├── keepAlive: 60 seg
├── clean_session: true
├── Suscripciones activas: ninguna (es publisher)
└── Mensajes pendientes: ninguno (QoS 0)

Cliente: subscriber-001
├── Estado: CONECTADO
├── Client ID: sub-001
├── keepAlive: 60 seg
├── clean_session: true
├── Suscripciones activas: campo/sensores (QoS 0)
└── Mensajes pendientes: ninguno
```

Con `clean_session=True` (default en el proyecto), al desconectarse el broker descarta todo ese estado. Con `clean_session=False` y QoS 1/2, el broker acumularía los mensajes que llegaron mientras el subscriber estuvo offline y los entregaría al reconectarse.

---

### 7.8 Resumen de lo que implementa el proyecto vs lo que podría implementar


| Mecanismo MQTT      | Estado en el proyecto        | Impacto si se omite                          |
| ------------------- | ---------------------------- | -------------------------------------------- |
| Client ID explícito | No (generado aleatoriamente) | Reflejado como .env en docker-compose        |
| QoS 0               | ✓ Implementado               | Posible pérdida de lecturas en red inestable |
| QoS 1               | No implementado              | Sin reenvío automático ante fallos           |
| QoS 2               | No implementado              | Aceptable para telemetría de monitoreo       |
| Retained messages   | No implementado              | Sin "último valor conocido" al conectar      |
| Last Will (LWT)     | No implementado              | No se detecta cuando un sensor falla         |
| clean_session=False | No implementado              | Sin entrega de mensajes acumulados offline   |
| Wildcards en topics | No implementado              | Requeriría reestructurar los topics          |


---

## 8. Por qué se usa MQTT para los sensores y REST para el frontend


| Necesidad                                          | Solución elegida            | Justificación                                                               |
| -------------------------------------------------- | --------------------------- | --------------------------------------------------------------------------- |
| El sensor necesita enviar datos constantemente     | MQTT (publish)              | Conexión persistente, bajo overhead, no espera respuesta                    |
| Múltiples sensores envían al mismo destino         | MQTT + broker               | El broker centraliza y distribuye sin que los sensores se conozcan entre sí |
| El suscriptor necesita reaccionar a cada dato      | MQTT (subscribe + callback) | El broker notifica en tiempo real; no hay polling                           |
| El frontend necesita datos históricos bajo demanda | REST GET /logs              | Petición puntual, respuesta inmediata, sin conexión persistente             |
| El frontend está en la web                         | REST sobre HTTP             | Los navegadores y librerías web hablan HTTP nativamente                     |


### Analogía

Imagina una estación meteorológica:

- **MQTT** es como una **radio que transmite** continuamente. Cualquier radio encendida en la misma frecuencia (topic) recibe los datos. El transmisor no sabe cuántas radios lo escuchan.
- **REST** es como **llamar por teléfono** para pedir el informe del tiempo. Llamas, preguntas, recibes la respuesta y cuelgas.

Ambos modelos tienen su lugar. Para un sensor que mide cada 3 segundos durante todo el día, la radio es más eficiente. Para un usuario que quiere ver el resumen cuando abre la app, la llamada telefónica es más apropiada.

---

## 9. Ciclo de vida completo de un dato

A continuación se traza el recorrido de un único dato desde que el sensor lo genera hasta que aparece en pantalla:

```
1. GENERACIÓN (sensor.py)
   ┌─────────────────────────────────────────────────────────┐
   │ data = {                                                │
   │   "sensor_id": "1",                                    │
   │   "temperatura": 22.45,                                │
   │   "humedad": 67.83                                     │
   │ }                                                       │
   └─────────────────────────────────────────────────────────┘
                         │
                         ▼ client.publish("campo/sensores", json.dumps(data))

2. TRANSPORTE MQTT (Mosquitto broker)
   ┌─────────────────────────────────────────────────────────┐
   │ Topic: campo/sensores                                   │
   │ Payload: {"sensor_id":"1","temperatura":22.45,...}      │
   │ QoS: 0 (fire and forget)                               │
   └─────────────────────────────────────────────────────────┘
                         │
                         ▼ broker entrega a todos los suscriptores del topic

3. RECEPCIÓN Y PERSISTENCIA (subscriber.py)
   ┌─────────────────────────────────────────────────────────┐
   │ on_message() → parsea JSON → agrega timestamp          │
   │ coleccion.insert_one(data)                             │
   │ MongoDB: agro_iot.lecturas                             │
   │ { sensor_id:"1", temperatura:22.45, timestamp:"..." } │
   └─────────────────────────────────────────────────────────┘
                         │
                         ▼ insert_one() en MongoDB

4. EXPOSICIÓN VÍA REST (rest_api/app.py)
   ┌─────────────────────────────────────────────────────────┐
   │ GET http://rest_api:5000/logs                           │
   │ coleccion.find().sort().limit(20)                      │
   │ Devuelve: HTTP 200 + JSON array de documentos          │
   └─────────────────────────────────────────────────────────┘
                         │
                         ▼ respuesta HTTP

5. VISUALIZACIÓN (frontend/app.py)
   ┌─────────────────────────────────────────────────────────┐
   │ requests.get("http://rest_api:5000/logs")              │
   │ → data = res.json()                                    │
   │ → st.text(line) por cada entrada                       │
   │ El usuario ve el dato en pantalla                      │
   └─────────────────────────────────────────────────────────┘
```

### Latencia del ciclo completo


| Etapa                                               | Protocolo   | Latencia típica |
| --------------------------------------------------- | ----------- | --------------- |
| Sensor → Broker                                     | MQTT TCP    | < 10 ms         |
| Broker → Subscriber                                 | MQTT TCP    | < 10 ms         |
| Subscriber → MongoDB                                | PyMongo TCP | < 5 ms          |
| Frontend → REST API                                 | HTTP TCP    | < 20 ms         |
| REST API → MongoDB                                  | PyMongo TCP | < 5 ms          |
| **Total (cuando el usuario presiona "Actualizar")** | —           | **< 50 ms**     |


El dato llega al archivo prácticamente en tiempo real. La "latencia" real la introduce el usuario al decidir cuándo presionar el botón — ahí está la diferencia conceptual entre MQTT (push continuo) y REST (pull bajo demanda).