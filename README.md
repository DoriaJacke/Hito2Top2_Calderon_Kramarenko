# IoT Agro Project

Demo de sensorización agrícola basado en **MQTT** + **REST API**. Simula dos sensores de campo que publican datos de temperatura y humedad, los persiste mediante un suscriptor MQTT, los expone con una API Flask y los muestra en un dashboard Streamlit.

---

## Arquitectura

```
[sensor1] ──┐
            ├──► [Mosquitto MQTT :1883] ──► [subscriber] ──► logs.txt (volumen compartido)
[sensor2] ──┘                                                      │
                                                                    ▼
[frontend :8501] ◄──── GET /logs ──── [rest_api :5000] ◄───────────┘
```

| Servicio    | Tecnología          | Puerto |
|-------------|---------------------|--------|
| `mqtt`      | Eclipse Mosquitto   | 1883   |
| `rest_api`  | Flask               | 5000   |
| `subscriber`| paho-mqtt (Python)  | —      |
| `sensor1/2` | paho-mqtt (Python)  | —      |
| `frontend`  | Streamlit           | 8501   |

---

## Requisitos previos

- [Docker](https://docs.docker.com/get-docker/) >= 20.10
- [Docker Compose](https://docs.docker.com/compose/install/) >= 2.0

Verificar instalación:

```bash
docker --version
docker compose version
```

---

## Estructura del proyecto

```
iot_agro_project/
├── docker-compose.yml
├── mosquitto.conf          # Configuración del broker MQTT
├── README.md
├── frontend/
│   ├── Dockerfile
│   └── app.py              # Dashboard Streamlit
├── mqtt_client/
│   ├── Dockerfile
│   └── subscriber.py       # Suscriptor MQTT → escribe logs
├── rest_api/
│   ├── Dockerfile
│   └── app.py              # API Flask GET /logs
└── sensors/
    ├── Dockerfile
    └── sensor.py           # Sensor simulado (temperatura + humedad)
```

---

## Instrucciones de ejecución

### 1. Clonar / posicionarse en el directorio

```bash
cd iot_agro_project
```

### 2. Construir y levantar todos los servicios

```bash
docker compose up --build
```

> La primera vez puede tardar varios minutos mientras se descargan las imágenes base y se instalan dependencias.

### 3. Verificar que los servicios están corriendo

```bash
docker compose ps
```

Deberías ver los 6 servicios con estado `Up` o `running`.

### 4. Abrir el dashboard

Abre el navegador en:

```
http://localhost:8501
```

Presiona el botón **"Actualizar"** para ver los últimos 20 registros recibidos por los sensores.

### 5. Consultar la API directamente (opcional)

```bash
curl http://localhost:5000/logs
```

Respuesta esperada: array JSON con líneas de log como:

```json
[
  "2024-06-01 12:00:03 - {'sensor_id': '1', 'temperatura': 22.5, 'humedad': 65.3}\n",
  "2024-06-01 12:00:06 - {'sensor_id': '2', 'temperatura': 18.1, 'humedad': 72.0}\n"
]
```

### 6. Ver logs de un servicio específico

```bash
# Logs del suscriptor MQTT
docker compose logs -f subscriber

# Logs de un sensor
docker compose logs -f sensor1

# Logs de la API
docker compose logs -f rest_api
```

### 7. Detener el proyecto

```bash
docker compose down
```

Para eliminar también el volumen de logs:

```bash
docker compose down -v
```

---

## Descripción de cada componente

### `sensors/sensor.py`
Simula un sensor de campo. Cada 3 segundos genera valores aleatorios de temperatura (10–35 °C) y humedad (30–90 %) y los publica en el topic MQTT `campo/sensores`. Con un 20 % de probabilidad simula un fallo de red y omite el envío.

### `mqtt_client/subscriber.py`
Se suscribe al topic `campo/sensores` y escribe cada mensaje recibido en `/app/shared/logs.txt` (volumen Docker compartido con la API).

### `rest_api/app.py`
API Flask con un único endpoint:

| Método | Ruta    | Descripción                          |
|--------|---------|--------------------------------------|
| GET    | `/logs` | Devuelve las últimas 20 líneas de log como array JSON |

### `frontend/app.py`
Dashboard Streamlit que consulta `GET /logs` al presionar el botón "Actualizar" y muestra los registros en pantalla.

### `mosquitto.conf`
Configura el broker Mosquitto para escuchar en el puerto 1883 y permitir conexiones anónimas (adecuado para entorno de laboratorio).

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| El frontend muestra lista vacía | Los sensores aún no enviaron datos | Esperar ~5 segundos y volver a presionar "Actualizar" |
| `Error: No se pudo conectar al backend` | La API no está lista | Verificar `docker compose logs rest_api` |
| Los sensores no se conectan | Mosquitto tardó en iniciar | Reiniciar: `docker compose restart sensor1 sensor2` |
| Puerto 8501 o 5000 ocupado | Otro proceso usa ese puerto | Cambiar el puerto en `docker-compose.yml` |

---

## Notas de diseño

- El archivo `logs.txt` reside en un **volumen Docker nombrado** (`logs_data`) montado en `/app/shared` tanto en el `subscriber` como en la `rest_api`. Esto garantiza que ambos contenedores accedan al mismo archivo.
- Las versiones de dependencias están fijadas en los `Dockerfile` para asegurar builds reproducibles.
- El servidor de desarrollo de Flask es suficiente para este demo; en producción se recomienda usar `gunicorn`.
