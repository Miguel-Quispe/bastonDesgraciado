"""
Servidor de Clonación de Voz de Optimus Prime (Blas García) usando Coqui XTTS v2.
Ejecuta este archivo en tu PC o servidor para que la aplicación móvil del bastón
hable con la voz auténtica de Optimus Prime en las respuestas de la IA.

Instalación previa en tu PC:
    pip install TTS flask

Uso:
    python servidor_optimus.py
"""

import os
from flask import Flask, request, send_file, jsonify
from TTS.api import TTS

app = Flask(__name__)

# Archivo de muestra de la voz de Blas García (Optimus Prime)
ARCHIVO_MUESTRA = "optimus_muestra.wav"
ARCHIVO_SALIDA = "temp_respuesta_optimus.wav"

print("==================================================")
print("🤖 Inicializando Coqui XTTS v2 con voz de Optimus Prime...")
print(f"🎙️ Muestra de audio de referencia: {ARCHIVO_MUESTRA}")
print("==================================================")

# Cargar modelo XTTS v2 una sola vez al inicio
tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)

@app.route("/", methods=["GET"])
def estado():
    return jsonify({
        "status": "online",
        "modelo": "XTTS_v2",
        "voz": "Blas García (Optimus Prime)"
    })

@app.route("/sintetizar", methods=["POST"])
def sintetizar():
    datos = request.get_json(force=True, silent=True) or {}
    texto = datos.get("texto", "").strip()

    if not texto:
        return jsonify({"error": "Texto vacío"}), 400

    print(f"\n[IA ➔ Optimus]: Sintetizando: '{texto}'")

    if not os.path.exists(ARCHIVO_MUESTRA):
        print(f"⚠️ AVISO: No se encontró '{ARCHIVO_MUESTRA}'. Coloca tu audio en esta carpeta.")
        return jsonify({"error": f"Falta {ARCHIVO_MUESTRA}"}), 404

    # Clonar la voz y guardar en archivo temporal
    tts.tts_to_file(
        text=texto,
        speaker_wav=ARCHIVO_MUESTRA,
        language="es",
        file_path=ARCHIVO_SALIDA
    )

    print(f"🔊 Audio generado con éxito: {ARCHIVO_SALIDA}")
    return send_file(ARCHIVO_SALIDA, mimetype="audio/wav")

if __name__ == "__main__":
    print("🚀 Servidor de voz de Optimus Prime escuchando en el puerto 5000.")
    print("👉 En tu app de celular pon la IP de tu PC, ejemplo: http://192.168.1.100:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
