import os
import sys
import base64
import requests
import json

def probar_minicpm(ruta_imagen, api_url="http://localhost:8000/v1/chat/completions", api_key="", prompt_personalizado=None):
    """
    Script de prueba para evaluar la capacidad de MiniCPM-V / MiniCPM-5 
    en la detección de obstáculos y descripción del entorno para personas con discapacidad visual.
    """
    print(f"--- Iniciando prueba de MiniCPM ---")
    print(f"Imagen: {ruta_imagen}")
    print(f"API Endpoint: {api_url}")

    if not os.path.exists(ruta_imagen):
        print(f"Error: La imagen '{ruta_imagen}' no existe.")
        return

    # 1. Codificar la imagen a Base64
    with open(ruta_imagen, "rb") as f:
        imagen_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = prompt_personalizado or (
        "Eres un asistente para una persona con discapacidad visual. "
        "Describe en 2 o 3 oraciones claras y directas en español qué obstáculos hay en el suelo, "
        "a qué distancia aproximada están y si el camino hacia adelante es seguro para caminar."
    )

    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": "openbmb/MiniCPM-V-2_6",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagen_b64}"}}
                ]
            }
        ],
        "max_tokens": 200,
        "temperature": 0.2
    }

    try:
        print("\nEnviando imagen a MiniCPM...")
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            respuesta_ia = data["choices"][0]["message"]["content"]
            print("\n=== RESPUESTA DE MINICPM ===")
            print(respuesta_ia)
            print("============================")
            return respuesta_ia
        else:
            print(f"Error del servidor (HTTP {response.status_code}): {response.text}")
    except requests.exceptions.ConnectionError:
        print("\n[AVISO]: No se pudo conectar con el servidor de MiniCPM en la URL indicada.")
        print("Asegúrate de tener un servidor local levantado (vLLM, Ollama, LM Studio) o una API en la nube.")
    except Exception as e:
        print(f"Error durante la prueba: {e}")

if __name__ == "__main__":
    # Si se pasa una imagen por parámetro, usarla
    archivo = sys.argv[1] if len(sys.argv) > 1 else "test_entorno.jpg"
    probar_minicpm(archivo)
