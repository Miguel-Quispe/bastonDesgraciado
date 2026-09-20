import os
import json
import datetime
import urllib.request
import urllib.parse
import threading
from kivy.clock import Clock

class AIAssistant:
    def __init__(self):
        self.archivo_config = os.path.join(os.getcwd(), "config_gemini.json")
        self.api_key = self._cargar_api_key()

    def _cargar_api_key(self):
        """Carga la API Key de Gemini desde variables de entorno o archivo de configuración."""
        env_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if env_key:
            return env_key
        try:
            if os.path.exists(self.archivo_config):
                with open(self.archivo_config, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("api_key", "").strip()
        except Exception as e:
            print(f"[AIAssistant] Error al cargar config API Key: {e}")
        return ""

    def guardar_api_key(self, nueva_key):
        """Guarda la API Key de forma persistente."""
        key_limpia = nueva_key.strip()
        self.api_key = key_limpia
        try:
            with open(self.archivo_config, "w", encoding="utf-8") as f:
                json.dump({"api_key": key_limpia}, f, ensure_ascii=False)
            print("[AIAssistant] Clave API de Gemini guardada correctamente.")
            return True
        except Exception as e:
            print(f"[AIAssistant] Error al guardar config API Key: {e}")
            return False

    def responder_consulta_local(self, texto_normalizado, texto_original):
        """Procesa preguntas comunes offline (hora, fecha, ayuda, identidad, sistema)."""
        texto = texto_normalizado

        # 1. Hora actual
        if any(w in texto for w in ["hora es", "la hora", "que hora", "dime la hora"]):
            ahora = datetime.datetime.now()
            hora_str = ahora.strftime("%I:%M %p").lower()
            hora_str = hora_str.replace("am", "de la mañana").replace("pm", "de la tarde")
            return f"Son las {hora_str}."

        # 2. Fecha actual
        if any(w in texto for w in ["fecha", "que dia es", "dia de hoy", "que fecha"]):
            ahora = datetime.datetime.now()
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            dia_nombre = dias[ahora.weekday()]
            mes_nombre = meses[ahora.month - 1]
            return f"Hoy es {dia_nombre} {ahora.day} de {mes_nombre}."

        # 3. Identidad y ayuda del asistente
        if any(w in texto for w in ["quien eres", "quien sos", "como te llamas", "tu funcion", "que haces", "que puedes hacer"]):
            return "Soy Bastón Inteligente, tu asistente de autonomía. Puedo detectar obstáculos con la cámara, guiarte a lugares, leer documentos, gestionar tu agenda y responder preguntas por voz."

        # 4. Estado de batería o sistema
        if any(w in texto for w in ["bateria", "nivel de carga", "estado del sistema"]):
            return "El asistente está activo y funcionando correctamente."

        return None

    def consultar_gemini_async(self, pregunta_texto, callback_respuesta):
        """Consulta la API de Gemini en un hilo secundario y devuelve la respuesta por callback."""
        def _hilo_gemini():
            respuesta = self._consultar_gemini_api(pregunta_texto)
            Clock.schedule_once(lambda dt: callback_respuesta(respuesta), 0)

        threading.Thread(target=_hilo_gemini, daemon=True).start()

    def _consultar_gemini_api(self, pregunta_texto):
        """Realiza la petición HTTP REST a Gemini Flash."""
        if not self.api_key:
            return "Puedo decirte la hora, la fecha, tu ubicación, leer documentos o consultar tu agenda. Si deseas hacerme cualquier pregunta libre, guarda tu clave API de Gemini diciendo 'guardar clave API' seguido de tu clave."

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={self.api_key}"

        
        prompt_sistema = (
            "Eres el asistente de voz de un bastón inteligente para personas no videntes. "
            "Responde a la siguiente consulta de forma muy breve, clara y amable en 1 o 2 oraciones sencillas en español. "
            "No uses viñetas, asteriscos, símbolos de marcas ni emojis, ya que tu respuesta se reproducirá por voz.\n\n"
            f"Pregunta del usuario: {pregunta_texto}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_sistema}
                    ]
                }
            ]
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})

        try:
            with urllib.request.urlopen(req, timeout=9) as response:
                if response.status == 200:
                    res_json = json.loads(response.read().decode("utf-8"))
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            txt = parts[0].get("text", "").strip()
                            txt_limpio = txt.replace("*", "").replace("#", "").replace("-", " ")
                            return txt_limpio
        except Exception as e:
            print(f"[AIAssistant] Error al consultar Gemini API: {e}")
            return "No pude conectar con la IA de Gemini en este momento. Verifica tu conexión a internet o tu clave API."

        return "No recibí respuesta de Gemini."
