import re
from flask import Flask, jsonify, request
import time
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ConnectionFailure

app = Flask(__name__)

# Claves de metadatos / tópico: no son variables de medición
_FIELD_META = frozenset(
    {
        "_id",
        "mqtt_topic",
        "zona_topic",
        "sensor_topic",
        "timestamp",
        "zona",
        "sensor",
        "published_ts_ms",
    }
)

_VAR_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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


mongo = conectar_mongo()
coleccion = mongo["agro_iot"]["lecturas"]


@app.route("/variables", methods=["GET"])
def variables():
    """Nombres de campos de medición vistos en las lecturas recientes."""
    try:
        n = min(int(request.args.get("muestra", 500)), 2000)
        if n < 1:
            n = 500
    except ValueError:
        n = 500
    try:
        keys = set()
        for doc in coleccion.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(n):
            for k in doc:
                if k not in _FIELD_META:
                    keys.add(k)
        return jsonify(sorted(keys))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/logs", methods=["GET"])
def logs():
    """
    Últimas 20 lecturas. Si se pasa ?variable=so2_ppm, solo documentos
    que incluyen ese campo (últimas 20 de esa variable).
    """
    raw = request.args.get("variable", "").strip()
    query = {}
    if raw:
        if not _VAR_NAME_RE.match(raw):
            return jsonify({"error": "nombre de variable inválido"}), 400
        query[raw] = {"$exists": True}
    try:
        docs = list(
            coleccion.find(query, {"_id": 0})
            .sort("timestamp", DESCENDING)
            .limit(20)
        )
        return jsonify(docs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/series", methods=["GET"])
def series():
    """
    Serie temporal por variable: últimos `limit` puntos por variable (cronológicos).
    Query: variables=so2_ppm,temperatura_c&limit=300
    """
    raw = request.args.get("variables", "")
    names = [v.strip() for v in raw.split(",") if v.strip()]
    if not names:
        return jsonify({})
    if len(names) > 16:
        return jsonify({"error": "máximo 16 variables por pedido"}), 400
    for v in names:
        if not _VAR_NAME_RE.match(v):
            return jsonify({"error": f"nombre de variable inválido: {v}"}), 400
    try:
        lim = int(request.args.get("limit", 300))
    except ValueError:
        lim = 300
    lim = max(10, min(lim, 2000))
    try:
        out = {}
        for v in names:
            proj = {"_id": 0, "timestamp": 1, v: 1}
            docs = list(
                coleccion.find({v: {"$exists": True}}, proj)
                .sort("timestamp", DESCENDING)
                .limit(lim)
            )
            docs.reverse()
            out[v] = [
                {"timestamp": d["timestamp"], "value": d.get(v)}
                for d in docs
                if d.get("timestamp") is not None
            ]
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
