from flask import Flask, jsonify
import time
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ConnectionFailure

app = Flask(__name__)

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

@app.route("/logs", methods=["GET"])
def logs():
    try:
        docs = list(
            coleccion.find({}, {"_id": 0})
                     .sort("timestamp", DESCENDING)
                     .limit(20)
        )
        return jsonify(docs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
