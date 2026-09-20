import os
import json
import datetime
import urllib.request
import urllib.parse
import threading
from kivy.clock import Clock

def _directorio_datos_app():
    """Devuelve el directorio de datos persistente seguro para Android y PC."""
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        if activity:
            files_dir = activity.getFilesDir()
            if files_dir:
                return files_dir.getAbsolutePath()
    except Exception:
        pass

    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, 'user_data_dir') and app.user_data_dir:
            return app.user_data_dir
    except Exception:
        pass

    return os.getcwd()

class AIAssistant:
    def __init__(self):
        self._config_nombre = "config_gemini.json"
        self.api_key_defecto = ""
        self.ultimo_error_config = ""
        self.api_key = self._cargar_api_key()

    @property
    def archivo_config(self):
        return os.path.join(_directorio_datos_app(), self._config_nombre)

    def _rutas_config_posibles(self):
        rutas = [self.archivo_config]
        ruta_local = os.path.join(os.getcwd(), self._config_nombre)
        if ruta_local not in rutas:
            rutas.append(ruta_local)
        return rutas

    def limpiar_api_key(self, api_key):
        """Normaliza una clave copiada desde teclado, portapapeles o voz."""
        if not api_key:
            return ""

        key = str(api_key).strip().strip('"').strip("'")
        for separador in ["api_key=", "api key=", "clave=", "key="]:
            if key.lower().startswith(separador):
                key = key[len(separador):].strip()
                break

        return "".join(key.split())

    def es_api_key_gemini_valida(self, api_key):
        """Validación local básica para evitar guardar claves de otro servicio."""
        key = self.limpiar_api_key(api_key)
        return key.startswith("AIza") and len(key) >= 30

    def _leer_api_key_desde_archivo(self, ruta):
        try:
            if not os.path.exists(ruta):
                return ""

            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read().strip()

            if not contenido:
                return ""

            try:
                data = json.loads(contenido)
                key_conf = data.get("api_key") or data.get("key") or data.get("gemini_api_key") or ""
            except Exception:
                key_conf = contenido

            return self.limpiar_api_key(key_conf)
        except Exception as e:
            print(f"[AIAssistant] Error al leer config API Key ({ruta}): {e}")
            return ""

    def _cargar_api_key(self):
        """Carga la API Key de Gemini desde variables de entorno, archivo de config o clave por defecto."""
        env_key = self.limpiar_api_key(os.environ.get("GEMINI_API_KEY", ""))
        if env_key and self.es_api_key_gemini_valida(env_key):
            return env_key

        for ruta in self._rutas_config_posibles():
            key_conf = self._leer_api_key_desde_archivo(ruta)
            if not key_conf:
                continue
            if self.es_api_key_gemini_valida(key_conf):
                print(f"[AIAssistant] API Key de Gemini cargada correctamente desde: {ruta}")
                return key_conf
            print(f"[AIAssistant] Config ignorada: la clave no parece ser de Gemini ({ruta}).")

        return self.api_key_defecto

    def guardar_api_key(self, nueva_key):
        """Guarda la API Key de forma persistente."""
        key_limpia = self.limpiar_api_key(nueva_key)
        self.ultimo_error_config = ""

        if not self.es_api_key_gemini_valida(key_limpia):
            self.ultimo_error_config = "La clave no parece ser de Gemini. Debe comenzar con AIza."
            print(f"[AIAssistant] {self.ultimo_error_config}")
            return False

        try:
            ruta = self.archivo_config
            carpeta = os.path.dirname(ruta)
            if carpeta:
                os.makedirs(carpeta, exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"api_key": key_limpia}, f, ensure_ascii=False)
            self.api_key = key_limpia
            print(f"[AIAssistant] Clave API guardada en: {ruta}")
            return True
        except Exception as e:
            self.ultimo_error_config = "No se pudo guardar la clave en el almacenamiento de la app."
            print(f"[AIAssistant] Error al guardar config API Key: {e}")
            return False

    def tiene_api_key_configurada(self):
        return self.es_api_key_gemini_valida(self.api_key)

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
        """Realiza la petición HTTP REST a Gemini Flash con modelos de respaldo."""
        key = self.api_key or self._cargar_api_key()
        if not key:
            return "La clave API de Gemini no está configurada. Abre configurar clave API y pega una clave válida que empiece con AIza."
        if not self.es_api_key_gemini_valida(key):
            return "La clave guardada no parece ser de Gemini. Borra esa clave y pega una clave válida que empiece con AIza."

        modelos = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-1.5-flash"]
        
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

        for model in modelos:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
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
                print(f"[AIAssistant] Error consultando {model}: {e}")
                continue

        return "No se pudo conectar con la IA de Gemini. Verifica que tu clave API sea válida (comienza por AIza) y tengas conexión a internet."

    def consultar_gemini_vision_async(self, ruta_imagen, prompt_instruccion, callback_respuesta):
        """Analiza una fotografía utilizando la API de Gemini Vision en un hilo secundario."""
        def _hilo_vision():
            respuesta = self._consultar_gemini_vision_api(ruta_imagen, prompt_instruccion)
            Clock.schedule_once(lambda dt: callback_respuesta(respuesta), 0)

        threading.Thread(target=_hilo_vision, daemon=True).start()

    def _consultar_gemini_vision_api(self, ruta_imagen, prompt_instruccion):
        if not self.es_api_key_gemini_valida(self.api_key):
            return None

        if not os.path.exists(ruta_imagen):
            print(f"[AIAssistant Vision] Archivo de imagen no existe: {ruta_imagen}")
            return None

        try:
            import base64
            with open(ruta_imagen, "rb") as img_f:
                b64_data = base64.b64encode(img_f.read()).decode("utf-8")

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={self.api_key}"

            prompt_sistema = (
                "Eres el asistente de visión de un bastón inteligente para personas no videntes. "
                "Responde de forma clara, directa y muy concisa en 1 o 2 oraciones sencillas en español. "
                "No uses viñetas, asteriscos, símbolos de marcado ni emojis, ya que tu respuesta se reproducirá por voz.\n\n"
                f"Instrucción para esta imagen: {prompt_instruccion}"
            )

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt_sistema},
                            {
                                "inlineData": {
                                    "mimeType": "image/jpeg",
                                    "data": b64_data
                                }
                            }
                        ]
                    }
                ]
            }

            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})

            with urllib.request.urlopen(req, timeout=12) as response:
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
            print(f"[AIAssistant Vision] Error al consultar Gemini Vision: {e}")

        return None
