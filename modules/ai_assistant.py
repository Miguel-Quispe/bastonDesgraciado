import datetime
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error
import threading
import socket
import ssl
try:
    from kivy.clock import Clock
except Exception:
    class Clock:
        @staticmethod
        def schedule_once(callback, delay=0):
            if delay <= 0:
                callback(0)
            else:
                threading.Timer(delay, lambda: callback(0)).start()

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

    try:
        home = os.path.expanduser("~")
        if home and os.path.isdir(home):
            baston_dir = os.path.join(home, ".bastonapp")
            os.makedirs(baston_dir, exist_ok=True)
            return baston_dir
    except Exception:
        pass

    return os.getcwd()

def obtener_nivel_bateria():
    """Obtiene el porcentaje real de batería y estado de carga en Android o PC."""
    # 1. Intentar en Android vía PyJNIus
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Intent = autoclass('android.content.Intent')
        IntentFilter = autoclass('android.content.IntentFilter')
        BatteryManager = autoclass('android.os.BatteryManager')
        activity = PythonActivity.mActivity

        filtro = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        estado_bateria = activity.registerReceiver(None, filtro)

        if estado_bateria:
            nivel = estado_bateria.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            escala = estado_bateria.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
            estado = estado_bateria.getIntExtra(BatteryManager.EXTRA_STATUS, -1)

            if nivel >= 0 and escala > 0:
                porcentaje = int((nivel / float(escala)) * 100)
                cargando = estado in [BatteryManager.BATTERY_STATUS_CHARGING, BatteryManager.BATTERY_STATUS_FULL]
                estado_str = "y está conectado al cargador" if cargando else "y no está cargando"
                return f"Tu nivel de batería es del {porcentaje} por ciento {estado_str}."
    except Exception as e:
        print(f"[AIAssistant] Error consultando batería en Android: {e}")

    # 2. Intentar en PC con psutil si está instalado
    try:
        import psutil
        bateria = psutil.sensors_battery()
        if bateria:
            porcentaje = int(bateria.percent)
            cargando = bateria.power_plugged
            estado_str = "y conectado a la corriente" if cargando else "con la batería"
            return f"Tu nivel de batería es del {porcentaje} por ciento {estado_str}."
    except Exception:
        pass

    return "No se pudo obtener el porcentaje de batería en este dispositivo."

class AIAssistant:
    MODELOS_OBSOLETOS = {
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
    }

    MODELOS_PRIORITARIOS = [
        "gemini-flash-lite-latest",
        "gemini-3-flash-preview",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-flash-latest",
    ]

    def __init__(self, directorio_datos=None):
        self._config_nombre = "config_gemini.json"
        self._directorio_personalizado = directorio_datos
        # Clave activa por defecto para que la app funcione directamente out-of-the-box
        self.api_key_defecto = ""
        self.ultimo_error_config = ""
        self.modelo_activo = "gemini-flash-lite-latest"
        self._modelos_detectados_cache = []
        self.claves_pool = []
        self.api_key = self._cargar_api_key()

    @property
    def archivo_config(self):
        if self._directorio_personalizado:
            return os.path.join(self._directorio_personalizado, self._config_nombre)
        return os.path.join(_directorio_datos_app(), self._config_nombre)

    def _rutas_config_posibles(self):
        rutas = []
        if self._directorio_personalizado:
            rutas.append(os.path.join(self._directorio_personalizado, self._config_nombre))

        # Directorio principal seguro
        rutas.append(self.archivo_config)

        # Kivy App user_data_dir si está activa
        try:
            from kivy.app import App
            app = App.get_running_app()
            if app and hasattr(app, 'user_data_dir') and app.user_data_dir:
                p = os.path.join(app.user_data_dir, self._config_nombre)
                if p not in rutas:
                    rutas.append(p)
        except Exception:
            pass

        # Android Activity getFilesDir
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            if activity:
                files_dir = activity.getFilesDir()
                if files_dir:
                    p = os.path.join(files_dir.getAbsolutePath(), self._config_nombre)
                    if p not in rutas:
                        rutas.append(p)
        except Exception:
            pass

        # Directorio local de trabajo
        ruta_local = os.path.join(os.getcwd(), self._config_nombre)
        if ruta_local not in rutas:
            rutas.append(ruta_local)

        # Directorios de usuario en el sistema
        try:
            home = os.path.expanduser("~")
            if home:
                rutas_home = [
                    os.path.join(home, ".bastonapp", self._config_nombre),
                    os.path.join(home, ".config", "bastonapp", self._config_nombre),
                    os.path.join(home, self._config_nombre)
                ]
                for rh in rutas_home:
                    if rh not in rutas:
                        rutas.append(rh)
        except Exception:
            pass

        return rutas

    def actualizar_directorio_datos(self, nuevo_directorio):
        """Permite vincular el user_data_dir de Kivy una vez que la App ha iniciado."""
        if nuevo_directorio:
            self._directorio_personalizado = nuevo_directorio
            self.recargar_api_key()

    def recargar_api_key(self):
        """Vuelve a comprobar todas las rutas de almacenamiento para cargar la clave guardada."""
        key = self._cargar_api_key()
        if key:
            self.api_key = key
        return self.api_key

    def limpiar_api_key(self, api_key):
        """Normaliza una clave copiada desde teclado, portapapeles o voz."""
        if not api_key:
            return ""

        key = str(api_key).strip().strip('"').strip("'")
        for separador in ["api_key=", "api key=", "clave=", "key="]:
            if key.lower().startswith(separador):
                key = key[len(separador):].strip()
                break

        key = key.replace("\\_", "_")
        return "".join(key.split())

    def es_api_key_gemini_valida(self, api_key):
        """Valida que la clave tenga el formato o longitud adecuada de Google AI Studio."""
        key = self.limpiar_api_key(api_key)
        if not key:
            return False
        return len(key) >= 15

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
                keys_list = data.get("api_keys") or []
                if isinstance(keys_list, list):
                    for k in keys_list:
                        k_limpia = self.limpiar_api_key(k)
                        if self.es_api_key_gemini_valida(k_limpia) and k_limpia not in self.claves_pool:
                            self.claves_pool.append(k_limpia)
            except Exception:
                key_conf = contenido

            # Si el contenido tiene varias claves separadas por coma, agregarlas al pool
            for token in re.split(r"[,;\s]+", contenido):
                t_limpio = self.limpiar_api_key(token)
                if self.es_api_key_gemini_valida(t_limpio) and t_limpio not in self.claves_pool:
                    self.claves_pool.append(t_limpio)

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
            print(f"[AIAssistant] Config ignorada: la clave no parece ser válida ({ruta}).")

        return self.api_key_defecto

    def guardar_api_key(self, nueva_key):
        """Guarda una o múltiples API Keys (separadas por coma o salto de línea) con soporte para pool."""
        self.ultimo_error_config = ""
        # Extraer todas las posibles claves enviadas
        partes = [self.limpiar_api_key(c) for c in re.split(r"[,;\s]+", str(nueva_key).strip())]
        claves_validas = [c for c in partes if self.es_api_key_gemini_valida(c)]

        if not claves_validas:
            self.ultimo_error_config = "La clave no parece ser válida. Debe tener al menos 15 caracteres."
            print(f"[AIAssistant] {self.ultimo_error_config}")
            return False

        key_principal = claves_validas[0]
        self.claves_pool = claves_validas
        guardado_exitoso = False

        # Guardar en todas las rutas posibles del dispositivo
        for ruta in self._rutas_config_posibles():
            try:
                carpeta = os.path.dirname(ruta)
                if carpeta:
                    os.makedirs(carpeta, exist_ok=True)
                with open(ruta, "w", encoding="utf-8") as f:
                    json.dump({
                        "api_key": key_principal,
                        "api_keys": claves_validas,
                    }, f, ensure_ascii=False)
                guardado_exitoso = True
                print(f"[AIAssistant] Clave(s) API guardada(s) en: {ruta}")
            except Exception as e:
                print(f"[AIAssistant] Aviso al guardar en {ruta}: {e}")

        if guardado_exitoso:
            self.api_key = key_principal
            return True
        else:
            self.ultimo_error_config = "No se pudo guardar la clave en el almacenamiento del dispositivo."
            return False

    def tiene_api_key_configurada(self):
        return self.es_api_key_gemini_valida(self.api_key)

    def _obtener_lista_claves(self):
        """Devuelve todas las claves API válidas para conmutación por fallo automática (failover)."""
        candidatas = []
        for k in (self.claves_pool or []):
            k_limpia = self.limpiar_api_key(k)
            if self.es_api_key_gemini_valida(k_limpia) and k_limpia not in candidatas:
                candidatas.append(k_limpia)
        if self.api_key:
            k_limpia = self.limpiar_api_key(self.api_key)
            if self.es_api_key_gemini_valida(k_limpia) and k_limpia not in candidatas:
                candidatas.append(k_limpia)
        cargada = self._cargar_api_key()
        if cargada:
            k_limpia = self.limpiar_api_key(cargada)
            if self.es_api_key_gemini_valida(k_limpia) and k_limpia not in candidatas:
                candidatas.append(k_limpia)
        if self.api_key_defecto:
            k_limpia = self.limpiar_api_key(self.api_key_defecto)
            if self.es_api_key_gemini_valida(k_limpia) and k_limpia not in candidatas:
                candidatas.append(k_limpia)
        return candidatas

    def _crear_request_gemini(self, model, payload, timeout_segundos=9, key=None):
        clave = self.limpiar_api_key(key or self.api_key or self._cargar_api_key())
        url = self._url_gemini(model, key=clave)
        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": clave,
        }
        return urllib.request.Request(url, data=data_bytes, headers=headers), timeout_segundos

    def _url_gemini(self, model, key=None):
        clave = self.limpiar_api_key(key or self.api_key or self._cargar_api_key())
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={clave}"

    def _headers_gemini(self, key=None):
        clave = self.limpiar_api_key(key or self.api_key or self._cargar_api_key())
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": clave,
        }

    def _extraer_texto_respuesta(self, res_json):
        candidates = res_json.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return ""
        txt = parts[0].get("text", "").strip()
        return txt.replace("*", "").replace("#", "").replace("-", " ")

    def _leer_respuesta_gemini(self, response):
        res_json = json.loads(response.read().decode("utf-8"))
        return self._extraer_texto_respuesta(res_json)

    def _obtener_modelos_candidatos(self):
        """Devuelve la lista ordenada de modelos candidatos válidos (excluyendo obsoletos y limitando a 4)."""
        candidatos = []
        if self.modelo_activo and self.modelo_activo not in self.MODELOS_OBSOLETOS:
            candidatos.append(self.modelo_activo)
        if self._modelos_detectados_cache:
            for m in self._modelos_detectados_cache:
                if m not in candidatos and m not in self.MODELOS_OBSOLETOS:
                    candidatos.append(m)
        for p in self.MODELOS_PRIORITARIOS:
            if p not in candidatos and p not in self.MODELOS_OBSOLETOS:
                candidatos.append(p)
        return candidatos[:4]

    def _detectar_modelos_disponibles_api(self):
        """Descubre automáticamente qué modelos Flash están activos y autorizados para la clave."""
        key = self.limpiar_api_key(self.api_key or self._cargar_api_key())
        if not key:
            return []
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        try:
            req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    detectados = []
                    for m in data.get("models", []):
                        nombre = m.get("name", "").replace("models/", "")
                        metodos = m.get("supportedGenerationMethods", [])
                        if (
                            "generateContent" in metodos 
                            and ("flash" in nombre or "gemini" in nombre) 
                            and "tts" not in nombre 
                            and "image" not in nombre
                            and nombre not in self.MODELOS_OBSOLETOS
                        ):
                            detectados.append(nombre)
                    # Reordenar según prioridad
                    ordenados = []
                    for p in self.MODELOS_PRIORITARIOS:
                        if p in detectados:
                            ordenados.append(p)
                    for o in detectados:
                        if o not in ordenados and o not in self.MODELOS_OBSOLETOS:
                            ordenados.append(o)
                    self._modelos_detectados_cache = ordenados
                    return ordenados
        except Exception as e:
            print(f"[AIAssistant] No se pudo auto-descubrir modelos: {e}")
        return []

    def _post_gemini(self, model, payload, timeout_segundos=9, key=None):
        """Hace la llamada a Gemini con requests; urllib queda como respaldo."""
        url = self._url_gemini(model, key=key)
        headers = self._headers_gemini(key=key)

        try:
            import requests
            import certifi
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout_segundos,
                verify=certifi.where(),
            )
            if response.status_code == 200:
                self.modelo_activo = model
                return self._extraer_texto_respuesta(response.json())

            self.ultimo_error_config = self._mensaje_error_api(response.status_code, response.text, model)
            print(f"[AIAssistant] Error Gemini {model}: HTTP {response.status_code} - {response.text}")
            return ""
        except Exception as requests_error:
            print(f"[AIAssistant] requests falló en {model}: {requests_error}. Intentando urllib...")

        req, timeout_urllib = self._crear_request_gemini(model, payload, timeout_segundos=timeout_segundos, key=key)
        try:
            with urllib.request.urlopen(req, timeout=timeout_urllib) as response:
                if response.status == 200:
                    self.modelo_activo = model
                    return self._leer_respuesta_gemini(response)
        except urllib.error.HTTPError as http_err:
            try:
                det = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                det = str(http_err)
            self.ultimo_error_config = self._mensaje_error_api(http_err.code, det, model)
            print(f"[AIAssistant] urllib error HTTP {http_err.code} en {model}: {det}")
        except Exception as e:
            self._registrar_error_gemini(model, e)
        return ""

    def _registrar_error_gemini(self, contexto, error):
        if isinstance(error, urllib.error.HTTPError):
            try:
                detalle = error.read().decode("utf-8", errors="replace")
            except Exception:
                detalle = str(error)
            self.ultimo_error_config = self._mensaje_error_api(error.code, detalle, contexto)
            print(f"[AIAssistant] Error Gemini {contexto}: HTTP {error.code} - {detalle}")
        else:
            self.ultimo_error_config = self._mensaje_error_conexion(error)
            print(f"[AIAssistant] Error Gemini {contexto}: {error}")

    def _mensaje_error_conexion(self, error):
        texto = str(error).lower()
        reason = getattr(error, "reason", None)
        if reason:
            texto = f"{texto} {reason}".lower()

        if isinstance(error, (socket.timeout, TimeoutError)) or "timed out" in texto or "timeout" in texto:
            return "Gemini tardó demasiado en responder. Revisa la señal WiFi o intenta otra vez."
        if isinstance(error, ssl.SSLError) or "certificate" in texto or "ssl" in texto:
            return "El celular no pudo validar el certificado HTTPS de Google. Revisa fecha, hora y certificados del dispositivo."
        if "name or service not known" in texto or "temporary failure in name resolution" in texto or "dns" in texto:
            return "El celular no pudo resolver la dirección de Google. Revisa DNS o el WiFi."
        if "network is unreachable" in texto or "no route to host" in texto or "failed to establish" in texto:
            return "El WiFi está conectado, pero Android no puede salir a internet desde la app."
        return f"No se pudo conectar con Gemini. Error técnico: {str(error)[:90]}"

    def _mensaje_error_api(self, codigo, detalle="", model=""):
        texto = str(detalle).lower()
        if codigo in [401, 403]:
            return "Google rechazó la clave API (HTTP 403). Verifica en aistudio.google.com que tu proyecto tenga acceso a la API."
        if codigo == 404:
            return f"El modelo {model or 'solicitado'} no está disponible en Google (HTTP 404)."
        if codigo == 429:
            return "La clave llegó al límite de cuota (HTTP 429). Revisa la cuota en Google AI Studio."
        if codigo == 503:
            return "Gemini está saturado temporalmente (HTTP 503). Intenta de nuevo en unos minutos."
        if "api key" in texto or "key" in texto:
            return "Google reportó un problema con la clave API."
        return f"Gemini respondió con error HTTP {codigo}."

    def probar_conexion_gemini_async(self, callback_resultado):
        """Prueba una llamada real a Gemini y devuelve (exito, mensaje) por callback."""
        def _hilo_prueba():
            exito, mensaje = self._probar_conexion_gemini()
            Clock.schedule_once(lambda dt: callback_resultado(exito, mensaje), 0)

        threading.Thread(target=_hilo_prueba, daemon=True).start()

    def _probar_conexion_gemini(self):
        self.ultimo_error_config = ""
        detectados = self._detectar_modelos_disponibles_api()
        if detectados:
            self.modelo_activo = detectados[0]

        respuesta = self._consultar_gemini_api("Responde exactamente con la palabra OK.")
        if respuesta and "no se pudo conectar" not in respuesta.lower() and "clave api" not in respuesta.lower() and "no está disponible" not in respuesta.lower():
            modelo_usado = self.modelo_activo or "Gemini Flash"
            return True, f"Clave API verificada y funcionando con {modelo_usado}. Gemini está 100% listo."

        if "cuota" in (self.ultimo_error_config or "").lower() or "429" in (self.ultimo_error_config or "") or "límite de peticiones" in (respuesta or "").lower():
            modelo_usado = self.modelo_activo or "gemini-flash-lite-latest"
            return True, f"Clave verificada con Google ({modelo_usado}). Cuota de peticiones alcanzada temporalmente; estará disponible enseguida."

        mensaje = self.ultimo_error_config or "Gemini no respondió. Revisa internet o permisos de la clave."
        return False, mensaje

    def responder_consulta_local(self, texto_normalizado, texto_original):
        """Procesa preguntas comunes offline (hora, fecha, ayuda, identidad, estado de batería)."""
        texto = texto_normalizado

        # 1. Hora actual
        if any(w in texto for w in ["hora es", "la hora", "que hora", "dime la hora"]):
            ahora = datetime.datetime.now()
            hora_str = ahora.strftime("%I:%M %p").lower()
            hora_str = hora_str.replace("am", "de la mañana").replace("pm", "de la tarde")
            return f"Son las {hora_str}."

        # 2. Fecha actual
        if any(w in texto for w in ["que dia es", "dia de hoy", "que fecha", "fecha de hoy"]) or ("fecha" in texto and not any(w in texto for w in ["festeja", "celebra", "ocurre"])):
            ahora = datetime.datetime.now()
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            dia_nombre = dias[ahora.weekday()]
            mes_nombre = meses[ahora.month - 1]
            return f"Hoy es {dia_nombre} {ahora.day} de {mes_nombre} del {ahora.year}."

        # 3. Nivel de batería real
        if any(w in texto for w in ["bateria", "carga", "pila", "porcentaje de bateria"]):
            return obtener_nivel_bateria()

        # 4. Identidad y ayuda del asistente
        if any(w in texto for w in ["quien eres", "quien sos", "como te llamas", "tu funcion", "que haces", "que puedes hacer"]):
            return "Soy Bastón Inteligente, tu asistente de autonomía. Puedo detectar obstáculos con la cámara, guiarte a lugares, leer documentos, gestionar tu agenda y responder preguntas por voz."

        return None

    def consultar_gemini_async(self, pregunta_texto, callback_respuesta):
        """Consulta la API de Gemini en un hilo secundario y devuelve la respuesta por callback."""
        def _hilo_gemini():
            respuesta = self._consultar_gemini_api(pregunta_texto)
            Clock.schedule_once(lambda dt: callback_respuesta(respuesta), 0)

        threading.Thread(target=_hilo_gemini, daemon=True).start()

    def _consultar_gemini_api(self, pregunta_texto):
        """Realiza la petición HTTP REST a Gemini Flash con modelos de respaldo y contexto temporal real."""
        key = self.api_key or self._cargar_api_key()
        if not key:
            return "La clave API de Gemini no está configurada. Abre configurar clave API y pega una clave válida de Google AI Studio."
        if not self.es_api_key_gemini_valida(key):
            return "La clave guardada no parece ser de Gemini. Borra esa clave y pega una clave válida de Google AI Studio."

        ahora = datetime.datetime.now()
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        fecha_humana = f"{dias[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]} de {ahora.year}"
        hora_humana = ahora.strftime("%H:%M")

        # Inyectar fecha y hora real para que Gemini nunca responda con fechas obsoletas como '4 de julio de 2024'
        prompt_sistema = (
            f"FECHA Y HORA ACTUALES EXACTAS DEL DISPOSITIVO: {fecha_humana}, {hora_humana}.\n"
            "Eres el asistente de voz de un bastón inteligente para personas con discapacidad visual en Bolivia/Latinoamérica. "
            "Responde a la siguiente consulta de forma concisa, veraz, clara y amable en 1 o máximo 2 oraciones sencillas en español. "
            "Si te preguntan qué se celebra, qué se festeja o qué día es hoy, básate estrictamente en la fecha actual suministrada. "
            "No uses asteriscos, viñetas, tablas, símbolos de marcado ni emojis, ya que tu respuesta se reproducirá directamente por voz del celular.\n\n"
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

        # Probar todas las claves disponibles (failover) con los modelos candidatos
        claves = self._obtener_lista_claves()
        modelos = self._obtener_modelos_candidatos()
        hubo_cuota = False
        
        for k in claves:
            for model in modelos:
                try:
                    txt_limpio = self._post_gemini(model, payload, timeout_segundos=7, key=k)
                    if txt_limpio:
                        self.api_key = k
                        self.modelo_activo = model
                        return txt_limpio
                    if "429" in (self.ultimo_error_config or "") or "cuota" in (self.ultimo_error_config or "").lower():
                        hubo_cuota = True
                except Exception as e:
                    self._registrar_error_gemini(model, e)
                    if "429" in (self.ultimo_error_config or ""):
                        hubo_cuota = True
                    continue

        if hubo_cuota:
            return "Las claves de Gemini alcanzaron el límite de peticiones por minuto. Espera un momento mientras se restablece la cuota."

        error_detalle = self.ultimo_error_config or "Verifica tu conexión a internet o tu clave API."
        return f"No se pudo conectar con Gemini. {error_detalle}"

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

            prompt_sistema = (
                "Eres el asistente de visión de un bastón inteligente para personas con discapacidad visual. "
                "Responde de forma clara, directa, útil y muy concisa en 1 o 2 oraciones sencillas en español. "
                "Describe la posición de obstáculos (izquierda, centro, derecha) y si el camino es seguro para avanzar. "
                "No uses viñetas, asteriscos, símbolos de marcado ni emojis, ya que tu respuesta se reproducirá por voz.\n\n"
                f"Instrucción para esta imagen: {prompt_instruccion}"
            )

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt_sistema},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": b64_data
                                }
                            }
                        ]
                    }
                ]
            }

            modelos = self._obtener_modelos_candidatos()
            for model in modelos:
                try:
                    txt_limpio = self._post_gemini(model, payload, timeout_segundos=10)
                    if txt_limpio:
                        return txt_limpio
                except Exception as e:
                    self._registrar_error_gemini(f"vision {model}", e)
        except Exception as e:
            print(f"[AIAssistant Vision] Error al consultar Gemini Vision: {e}")

        return None
