# Monitoreo minero — Zona Sur (Calderón Kramarenko)

Proyecto de demostración **IoT** para una zona minera simulada: varios **publicadores MQTT** (sensores simulados) envían telemetría por **AWS IoT Core**, un **suscriptor** persiste las lecturas en **MongoDB**, una **API REST** expone consultas y un **dashboard Streamlit** muestra tabla y gráficos de tendencia. Incluye **Prometheus** y **Grafana** para métricas operativas (latencia, frecuencia, volumen).

---

## Arquitectura

```
[sensores N] ──TLS/MQTT──► AWS IoT Core ──TLS/MQTT──► [subscriber] ──► MongoDB (agro_iot.lecturas)
       ▲                                                    │
       │                                                    │ métricas :8000/metrics
       │                                                    ▼
       │                                            [Prometheus] ──► [Grafana :3000]

[frontend :8501] ──HTTP──► [rest_api :5000] ──► MongoDB
```

| Servicio | Rol | Puerto (host) |
|----------|-----|-----------------|
| `mongodb` | Base de datos | 27017 |
| `subscriber` | Suscripción MQTT → inserts en Mongo + métricas Prometheus | 8000 (`/metrics`) |
| `rest_api` | Flask: `/logs`, `/variables`, `/series` | 5000 |
| `sensor_*` | Publicadores simulados (uno por variable de medición) | — |
| `frontend` | Streamlit: tabla + tendencias (Plotly) | 8501 |
| `mongodb_exporter` | Métricas MongoDB para Prometheus | 9216 |
| `prometheus` | Recolección de series temporales | 9090 |
| `grafana` | Dashboards (usuario/contraseña por defecto `admin` / `admin`) | 3000 |

El broker MQTT en la nube es **AWS IoT Core** (no Mosquitto local). Los tópicos siguen la forma `mina/<zona>/<sensor>` (por ejemplo `mina/zona_sur_calderon_kramarenko/so2`).

---

## Requisitos previos

- [Docker](https://docs.docker.com/get-docker/) y [Docker Compose](https://docs.docker.com/compose/install/) v2
- Credenciales **AWS IoT** (CA, certificado de dispositivo y clave privada) en la carpeta **`certs/`** (no se versiona; está en `.gitignore`). Los nombres de archivo deben coincidir con las variables del `docker-compose.yml` (anchor `x-aws-iot-tls`) o renombrá los PEM y ajustá esas variables.

```bash
docker --version
docker compose version
```

---

## Estructura del repositorio

```
├── docker-compose.yml
├── prometheus/
│   └── prometheus.yml          # Scrapes: subscriber, mongodb_exporter
├── grafana/
│   ├── provisioning/           # Datasource Prometheus + dashboards
│   └── dashboards/
│       └── iot-observability.json
├── certs/                      # AWS IoT TLS (local, no en git)
├── sensors/
│   ├── Dockerfile
│   └── sensor.py               # Simulación por tipo de sensor → publish MQTT
├── mqtt_client/
│   ├── Dockerfile
│   └── subscriber.py           # MQTT → MongoDB + /metrics (Prometheus)
├── rest_api/
│   ├── Dockerfile
│   └── app.py                  # Flask + PyMongo
├── frontend/
│   ├── Dockerfile
│   └── app.py                  # Streamlit + Plotly
└── README.md
```

---

## Puesta en marcha

### 1. Certificados

Colocá en `certs/` los archivos de TLS que uses en `docker-compose.yml` (`AWS_IOT_CA_FILE`, `AWS_IOT_CERT_FILE`, `AWS_IOT_KEY_FILE`).

### 2. Levantar el stack

```bash
cd Hito2Top2_Calderon_Kramarenko   # o la ruta donde clonaste el repo
docker compose up --build -d
```

La primera ejecución puede tardar por imágenes y builds.

### 3. Comprobar servicios

```bash
docker compose ps
```

Deberías ver contenedores en estado `running` (MongoDB, API, suscriptor, sensores, frontend, Prometheus, Grafana, exporter).

### 4. URLs útiles

| Qué | URL |
|-----|-----|
| Dashboard Streamlit | http://localhost:8501 |
| API REST | http://localhost:5000 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / admin en demo) |
| Métricas del suscriptor | http://localhost:8000/metrics |

En el frontend: primero se muestra la **tabla** de últimas lecturas; debajo, **tendencias** con grilla de **2 columnas** y **30 puntos** por variable seleccionada. El botón **Actualizar datos** fuerza un refresco desde el servidor.

### 5. API (ejemplos)

```bash
# Últimas 20 lecturas (todas o filtradas por campo presente en el documento)
curl "http://localhost:5000/logs"
curl "http://localhost:5000/logs?variable=so2_ppm"

# Nombres de campos de medición vistos en documentos recientes
curl "http://localhost:5000/variables"

# Series temporales (hasta 16 variables; limit entre 10 y 2000)
curl "http://localhost:5000/series?variables=so2_ppm,temperatura_c&limit=30"
```

La respuesta de `/logs` es un **array de documentos** JSON (campos como `timestamp`, `mqtt_topic`, métricas según sensor), no líneas de texto de log.

### 6. Logs de contenedores

```bash
docker compose logs -f subscriber
docker compose logs -f rest_api
docker compose logs -f sensor_so2
```

### 7. Detener y limpiar

```bash
docker compose down
```

Para borrar también los datos persistentes de MongoDB:

```bash
docker compose down -v
```

---

## Componentes (resumen)

### `sensors/sensor.py`

Simula un sensor según `SENSOR_NAME` (temperatura, humedad, SO₂, etc.). Cada ~3 s publica JSON en `mina/<MQTT_ZONE>/<SENSOR_NAME>` con TLS hacia AWS IoT. Incluye `published_ts_ms` para estimar latencia en el suscriptor. Con ~20 % de probabilidad simula fallo de red y no publica.

### `mqtt_client/subscriber.py`

Se suscribe al comodín configurado (por defecto `mina/zona_sur_calderon_kramarenko/#`), inserta documentos en `agro_iot.lecturas` y expone métricas **Prometheus** en el puerto configurado (`METRICS_PORT`, por defecto 8000).

### `rest_api/app.py`

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/logs` | Últimas 20 lecturas; query opcional `variable=<campo>` |
| GET | `/variables` | Lista de nombres de campos de medición detectados |
| GET | `/series` | Series por variable: `variables=a,b&limit=N` |

### `frontend/app.py`

Consulta la API (`REST_API_URL`, por defecto `http://rest_api:5000` en Docker). Tabla en formato largo (variable / valor) y gráficos Plotly alimentados por `/series`.

### Observabilidad (Prometheus / Grafana)

- **Prometheus** scrapea el suscriptor (`:8000`) y **mongodb_exporter** (`:9216`).
- El exporter debe llevar **`--collector.collstats`** junto con **`--mongodb.collstats-colls=agro_iot.lecturas`**; si no, Grafana mostrará *No data* en paneles basados en `$collStats`.
- Dashboard de ejemplo: *Hito2 — Latencia, frecuencia y volumen* (provisionado en Grafana).

---

## Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---------|-----------------|-----------|
| Frontend no conecta al backend | API caída o URL incorrecta fuera de Docker | Revisar `docker compose logs rest_api`; si corrés Streamlit en el host, definí `REST_API_URL=http://localhost:5000`. |
| Sin datos en Mongo / API vacía | Certificados IoT o endpoint incorrectos | Revisar logs de `subscriber` y sensores; validar `certs/` y variables AWS en compose. |
| Grafana *No data* en paneles MongoDB | Exporter sin collector collstats | Confirmar en `docker-compose.yml` las flags `--collector.collstats` y `--mongodb.collstats-colls=agro_iot.lecturas`. |
| `dockerDesktopLinuxEngine` / error de pipe | Docker Desktop no iniciado | Arrancar Docker Desktop y esperar a que el motor esté listo. |
| Puerto 8501, 5000, 3000 u ocupado | Otro proceso usa el puerto | Cambiar el mapeo `puerto_host:puerto_contenedor` en `docker-compose.yml`. |

---

## Notas

- El servidor de desarrollo de Flask es adecuado para la demo; en producción conviene un WSGI (por ejemplo Gunicorn) y autenticación en la API.
- Cambiá las credenciales por defecto de **Grafana** si exponés los puertos a una red no confiable.
- Las dependencias de Python están fijadas en los `Dockerfile` para builds reproducibles.
