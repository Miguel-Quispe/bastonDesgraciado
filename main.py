import os
import time
try:
    import qrcode
except ImportError:
    qrcode = None

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp

from modules.bluetooth_manager import BluetoothManager
from modules.speech_engine import SpeechEngine, normalizar_texto
from modules.location_service import LocationService
from modules.vision_analyzer import VisionAnalyzer
from modules.agenda_manager import AgendaManager
from modules.document_reader import DocumentReader
from modules.ai_assistant import AIAssistant, obtener_nivel_bateria

class BastonApp(App):
    def build(self):
        self.title = "Bastón Inteligente - Asistente Autónomo"
        Window.clearcolor = (0.05, 0.08, 0.12, 1)
        Window.softinput_mode = 'pan'

        self.bt = BluetoothManager()
        self.voz = SpeechEngine()
        self.gps = LocationService()
        self.vision = VisionAnalyzer()
        self.agenda = AgendaManager()
        self.lector = DocumentReader()
        self.ai = AIAssistant()
        
        self.evento_navegacion = None
        self._analizando_camino = False
        self._ultima_frase_guia = ""
        self._wake_lock = None
        self._camara_en_uso_por_comando = False
        self._ultimo_toque_tiempo = 0

        # Vincular toque en cualquier parte de la pantalla para accesibilidad (cancelar ruta con toque)
        Window.bind(on_touch_down=self.al_tocar_pantalla)

        self.layout = BoxLayout(
            orientation='vertical',
            padding=[dp(16), dp(14), dp(16), dp(16)],
            spacing=dp(10)
        )

        # ── Etiqueta de estado principal ──────────────────────────────────────
        self.lbl_estado = Label(
            text="Asistente de Autonomía\nEscucha activa",
            font_size='20sp',
            bold=True,
            color=(1, 1, 1, 1),
            halign='center',
            valign='middle',
            size_hint=(1, 1)
        )
        self.lbl_estado.bind(size=self.lbl_estado.setter('text_size'))
        self.layout.add_widget(self.lbl_estado)

        self.img_qr = Image(
            size_hint=(1, None),
            height=0,
            opacity=0
        )
        self.layout.add_widget(self.img_qr)

        # ── Panel de configuración de clave API (oculto por defecto) ──────────
        self.panel_api = BoxLayout(
            orientation='vertical',
            spacing=dp(6),
            size_hint=(1, None),
            height=0,
            opacity=0
        )

        lbl_api_titulo = Label(
            text="Clave API de Gemini",
            font_size='17sp',
            bold=True,
            color=(0.9, 0.8, 0.2, 1),
            size_hint=(1, None),
            height=dp(30),
            halign='center'
        )
        lbl_api_titulo.bind(size=lbl_api_titulo.setter('text_size'))
        self.panel_api.add_widget(lbl_api_titulo)

        self.input_api_key = TextInput(
            hint_text="Pega aquí tu clave API de Gemini...",
            font_size='15sp',
            multiline=False,
            size_hint=(1, None),
            height=dp(48),
            background_color=(0.12, 0.16, 0.22, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.9, 0.8, 0.2, 1),
            padding=[dp(10), dp(12)]
        )
        self.panel_api.add_widget(self.input_api_key)

        self.btn_pegar_api = Button(
            text="Pegar Clave del Portapapeles",
            font_size='15sp',
            bold=True,
            size_hint=(1, None),
            height=dp(44),
            background_normal='',
            background_color=(0.15, 0.55, 0.45, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_pegar_api.bind(on_press=self.al_pegar_api_key_clipboard)
        self.panel_api.add_widget(self.btn_pegar_api)

        self.btn_guardar_api = Button(
            text="Guardar Clave API",
            font_size='17sp',
            bold=True,
            size_hint=(1, None),
            height=dp(48),
            background_normal='',
            background_color=(0.1, 0.5, 0.85, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_guardar_api.bind(on_press=self.al_guardar_api_key_ui)
        self.panel_api.add_widget(self.btn_guardar_api)

        self.layout.add_widget(self.panel_api)

        # ── Botón de configuración (engranaje) ────────────────────────────────
        self.btn_config = Button(
            text="Configurar Clave API",
            font_size='16sp',
            size_hint=(1, None),
            height=dp(44),
            background_normal='',
            background_color=(0.18, 0.22, 0.30, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_config.bind(on_press=self.al_toggle_panel_api)
        self.layout.add_widget(self.btn_config)

        # ── Botón principal indicador de escucha continua ─────────────────────
        self.btn_accion = Button(
            text="ESCUCHA ACTIVA\nHabla libremente",
            font_size='19sp',
            bold=True,
            size_hint=(1, None),
            height=dp(118),
            background_normal='',
            background_color=(0.1, 0.65, 0.45, 1),
            color=(1, 1, 1, 1),
            halign='center',
            valign='middle'
        )
        self.btn_accion.bind(size=self.btn_accion.setter('text_size'))
        self.btn_accion.bind(on_press=self.al_presionar_boton_escucha)
        self.layout.add_widget(self.btn_accion)

        return self.layout

    def al_tocar_pantalla(self, window, touch):
        """
        Accesibilidad táctil: Si la navegación está activa, un toque deliberado
        en cualquier parte de la pantalla cancela inmediatamente la ruta.
        """
        if self.gps.navegacion_activa:
            ahora = time.time()
            if ahora - self._ultimo_toque_tiempo > 0.5:
                self._ultimo_toque_tiempo = ahora
                self.cancelar_navegacion_activa("por toque en pantalla")
                return True
        return False

    def cancelar_navegacion_activa(self, motivo=""):
        """Detiene la guía peatonal y devuelve la cámara al modo espera o gestos."""
        if not self.gps.navegacion_activa and not self.evento_navegacion:
            return

        self.gps.cancelar_navegacion()
        if self.evento_navegacion:
            self.evento_navegacion.cancel()
            self.evento_navegacion = None

        self._camara_en_uso_por_comando = False
        self._analizando_camino = False
        self.btn_accion.text = "ESCUCHA ACTIVA\nHabla libremente"
        self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
        self.lbl_estado.text = "Navegación cancelada."

        self.emitir_vibracion_bienvenida()
        if "gesto" in motivo:
            self.voz.hablar("Ruta cancelada por gesto de mano. Listo para nueva orden.")
        else:
            self.voz.hablar("Navegación y copiloto visual cancelados.")
        self.programar_reinicio_control_por_gesto()

    def al_toggle_panel_api(self, instance):
        if self.panel_api.opacity == 0:
            clave_actual = self.ai.api_key or ""
            self.input_api_key.text = clave_actual
            self.panel_api.height = dp(186)
            self.panel_api.opacity = 1
            self.btn_config.text = "Cerrar Configuración"
            self.btn_config.background_color = (0.45, 0.1, 0.1, 1)
        else:
            self.panel_api.height = 0
            self.panel_api.opacity = 0
            self.btn_config.text = "Configurar Clave API"
            self.btn_config.background_color = (0.18, 0.22, 0.30, 1)

    def al_pegar_api_key_clipboard(self, instance):
        try:
            from kivy.core.clipboard import Clipboard
            texto = Clipboard.paste()
            if texto and texto.strip():
                self.input_api_key.text = texto.strip()
                self.lbl_estado.text = "Clave pegada. Presiona 'Guardar Clave API'."
                self.voz.hablar("Clave pegada del portapapeles. Presiona guardar.")
            else:
                self.lbl_estado.text = "El portapapeles está vacío. Copia la clave de AI Studio primero."
                self.voz.hablar("El portapapeles está vacío. Copia la clave primero.")
        except Exception as e:
            self.lbl_estado.text = f"Error al acceder al portapapeles: {e}"

    def al_guardar_api_key_ui(self, instance):
        nueva_key = self.input_api_key.text.strip()
        if not nueva_key:
            self.lbl_estado.text = "Escribe la clave API antes de guardar."
            return

        exito = self.ai.guardar_api_key(nueva_key)
        if exito:
            self.lbl_estado.text = "Clave guardada. Probando conexión con Gemini..."
            self.voz.hablar("Clave guardada. Probando conexión con Gemini.")
            self.ai.probar_conexion_gemini_async(self.al_resultado_prueba_api)
        else:
            detalle = getattr(self.ai, 'ultimo_error_config', '') or "Verifica que sea una clave API de Gemini válida."
            self.lbl_estado.text = f"Error al guardar la clave. {detalle}"
            self.voz.hablar(detalle)

    def al_resultado_prueba_api(self, exito, mensaje):
        if exito:
            self.lbl_estado.text = "Clave API de Gemini conectada correctamente."
            self.voz.hablar(mensaje)
            if self.panel_api.opacity != 0:
                self.al_toggle_panel_api(None)
        else:
            self.lbl_estado.text = f"Gemini no respondió: {mensaje}"
            self.voz.hablar(mensaje)

    def solicitar_permisos_android(self):
        try:
            from android.permissions import request_permissions, Permission
            permisos = [
                Permission.CAMERA,
                Permission.RECORD_AUDIO,
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION,
            ]
            try:
                permisos.append(Permission.BLUETOOTH_CONNECT)
                permisos.append(Permission.BLUETOOTH_SCAN)
            except AttributeError:
                pass
            
            def callback_permisos(permissions, grants):
                audio_concedido = True
                camara_concedida = True
                try:
                    for permiso, concedido in zip(permissions, grants):
                        permitido = concedido if isinstance(concedido, bool) else int(concedido) == 0
                        if str(permiso).endswith("RECORD_AUDIO"):
                            audio_concedido = permitido
                        elif str(permiso).endswith("CAMERA"):
                            camara_concedida = permitido
                except Exception:
                    pass

                self.permiso_camara_concedido = camara_concedida
                if not audio_concedido:
                    self.lbl_estado.text = "Permiso de micrófono denegado. Actívalo para usar comandos de voz."
                    self.voz.hablar("Permiso de micrófono denegado. Actívalo en ajustes.")
                    return

                Clock.schedule_once(lambda dt: self.iniciar_control_por_gesto(), 1.0)

            request_permissions(permisos, callback_permisos)
        except Exception as e:
            print(f"[BastonApp] Permisos nativos: {e}")

    def emitir_vibracion_bienvenida(self):
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            activity = PythonActivity.mActivity
            vibrator = activity.getSystemService(Context.VIBRATOR_SERVICE)
            if vibrator:
                vibrator.vibrate(250)
        except Exception:
            pass

    def on_start(self):
        self.solicitar_permisos_android()
        self.emitir_vibracion_bienvenida()
        self.mantener_activa_con_pantalla_apagada()

        try:
            from android import activity
            activity.bind(on_activity_result=self.al_recibir_resultado_actividad)
        except Exception:
            pass

        try:
            self.bt.iniciar_auto_reconexion(self.al_recibir_alerta_baston, self.al_cambio_estado_baston)
        except Exception as e:
            print(f"[BastonApp] Bluetooth auto-reconexion: {e}")

        mensaje_bienvenida = "Asistente listo. Muestra tu palma abierta frente a la cámara trasera para dar un comando."
        try:
            self.voz.hablar(mensaje_bienvenida, perfil="animada")
        except Exception:
            pass

        self.lbl_estado.text = "Muestra la palma abierta frente a la cámara para ordenar."
        self.btn_accion.text = "CONTROL POR GESTO ACTIVO\nMuestra tu palma abierta o toca aquí"
        self.btn_accion.background_color = (0.1, 0.5, 0.7, 1)

    def iniciar_control_por_gesto(self):
        if not self.voz.activity or self._camara_en_uso_por_comando or self.gps.navegacion_activa:
            return
        iniciado = self.vision.iniciar_detector_gesto(self.activar_comando_por_gesto)
        if iniciado:
            self.lbl_estado.text = "Cámara trasera activa. Muestra la palma abierta para dar un comando."
            self.btn_accion.text = "ESPERANDO PALMA ABIERTA\nMuestra tu mano abierta para hablar"
            self.btn_accion.background_color = (0.1, 0.45, 0.7, 1)
        else:
            self.lbl_estado.text = "Asistente listo. Presiona el botón para dar una orden."
            self.btn_accion.text = "TOCA PARA HABLAR\nPresiona para dar un comando"
            self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)

    def activar_comando_por_gesto(self):
        """Se activa al ver la palma abierta: detiene la cámara y abre el micrófono de inmediato."""
        self.lbl_estado.text = "¡Palma detectada! Abriendo micrófono..."
        self.btn_accion.text = "ABRIENDO MICRÓFONO...\nEspera un segundo"
        self.btn_accion.background_color = (0.8, 0.5, 0.1, 1)
        self.voz.detener_voz()
        self.vision.detener_detector_gesto()
        Clock.schedule_once(lambda dt: self._abrir_comando_por_gesto(), 0.15)

    def _abrir_comando_por_gesto(self):
        def _al_finalizar_escucha():
            self.programar_reinicio_control_por_gesto()

        self.voz.detener_voz()
        if self.voz.escuchar_una_vez(self.procesar_comando_texto, _al_finalizar_escucha):
            self.lbl_estado.text = "Micrófono activo. Di tu comando ahora..."
            self.btn_accion.text = "MICRÓFONO ACTIVO\nTe escucho, di tu comando..."
            self.btn_accion.background_color = (0.85, 0.2, 0.2, 1)
            self.emitir_vibracion_bienvenida()
        else:
            self.lbl_estado.text = "Micrófono no disponible. Reintentando..."
            Clock.schedule_once(lambda dt: self.iniciar_control_por_gesto(), 1.0)

    def programar_reinicio_control_por_gesto(self):
        Clock.schedule_once(lambda dt: self._reanudar_control_por_gesto_si_libre(), 0.25)

    def _reanudar_control_por_gesto_si_libre(self):
        if self._camara_en_uso_por_comando or self.gps.navegacion_activa:
            return
        espera_voz = getattr(self.voz, '_bloqueo_eco_hasta', 0.0) - time.monotonic()
        if espera_voz > 0:
            Clock.schedule_once(lambda dt: self._reanudar_control_por_gesto_si_libre(), espera_voz + 0.25)
            return
        self.iniciar_control_por_gesto()

    def mantener_activa_con_pantalla_apagada(self):
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            PowerManager = autoclass('android.os.PowerManager')
            activity = PythonActivity.mActivity
            power_manager = activity.getSystemService(Context.POWER_SERVICE)
            self._wake_lock = power_manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "BastonInteligente:Asistencia")
            self._wake_lock.setReferenceCounted(False)
            self._wake_lock.acquire()
        except Exception:
            pass

    def al_recibir_resultado_actividad(self, request_code, result_code, intent_data):
        if request_code == 1001 and result_code == -1 and intent_data:
            try:
                from jnius import autoclass
                RecognizerIntent = autoclass('android.speech.RecognizerIntent')
                matches = intent_data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                if matches and matches.size() > 0:
                    texto = str(matches.get(0)).strip()
                    self.lbl_estado.text = f"Escuchado: {texto}"
                    self.voz._procesar_texto_reconocido(texto, self.procesar_comando_texto)
            except Exception as e:
                print(f"[BastonApp] Intent voz error: {e}")

        elif request_code == 1002 and result_code == -1:
            self.lbl_estado.text = "Procesando foto del entorno..."
            Clock.schedule_once(lambda dt: self.vision.procesar_foto_capturada(), 0.5)

        elif request_code == 1003 and result_code == -1:
            self.lbl_estado.text = "Procesando lectura del documento..."
            Clock.schedule_once(lambda dt: self.lector.procesar_foto_capturada(), 0.5)

        elif request_code == 1002:
            self.vision.cancelar_captura("No pude abrir la cámara trasera.")

        elif request_code == 1003:
            self.lector.cancelar_captura("No pude abrir la cámara para leer el documento.")

    def al_presionar_boton_escucha(self, instance):
        if self.gps.navegacion_activa:
            self.cancelar_navegacion_activa("por botón táctil")
            return

        self.vision.detener_detector_gesto()
        self.activar_comando_por_gesto()

    def al_recibir_parcial(self, texto_parcial):
        if texto_parcial:
            self.lbl_estado.text = f"Oyendo: {texto_parcial}..."

    def procesar_comando_texto(self, texto_comando):
        if not texto_comando:
            return

        texto = normalizar_texto(texto_comando)
        if not texto:
            return

        print(f"[Comando]: '{texto_comando}' (norm: '{texto}')")
        self.lbl_estado.text = f"Comando: {texto_comando}"
        self.img_qr.opacity = 0
        self.img_qr.height = 0

        # NODO 0A: Presentación Oficial del Proyecto ante el Jurado
        if any(w in texto for w in ["presentar proyecto", "presentacion", "presentate", "saludo jurado", "explicar proyecto", "que es este proyecto"]):
            intro_jurado = (
                "¡Hola, distinguidos miembros del jurado! Soy el copiloto inteligente de asistencia y navegación "
                "para personas con discapacidad visual. Cuento con detección ultrasónica en el bastón, visión artificial por cámara "
                "para detección de obstáculos y lectura de documentos, además de inteligencia artificial. ¡El bastón inteligente se encuentra en línea y listo para la demostración!"
            )
            self.lbl_estado.text = "Presentando proyecto al jurado..."
            self.voz.hablar_respuesta_ia(intro_jurado)
            return

        # NODO 0: Saludo y Activación por voz
        if any(w in texto for w in ["hola", "saludo", "buenas", "activado", "estas ahi", "ayuda", "quien eres"]):
            nombre_act = self.voz.nombre_asistente.capitalize()
            self.voz.hablar(f"¡Hola! Soy tu {nombre_act} de asistencia. ¡Te escucho! Puedo ayudarte con la cámara, agenda, batería, ubicación, guiado de ruta o responder cualquier duda.", perfil="animada")
            self.lbl_estado.text = "Asistente activo. ¡Te escucho!"
            return

        # NODO 1: Batería Actual (Respuesta inmediata precisa con nivel real)
        if any(w in texto for w in ["bateria", "carga", "pila", "nivel de bateria", "bateria actual", "cuanta bateria", "que bateria"]):
            estado_bat = obtener_nivel_bateria()
            self.lbl_estado.text = estado_bat
            self.voz.hablar(estado_bat)
            return

        # NODO 2: Cancelar Navegación Activa (por voz)
        if any(w in texto for w in ["cancelar ruta", "detener guia", "parar ruta", "cancelar navegacion", "detener navegacion", "cancelar guia", "detener copiloto", "detener", "para", "cancela", "cancelar"]):
            if self.gps.navegacion_activa:
                self.cancelar_navegacion_activa("por orden de voz")
                return

        # NODO 3: Ajustes de la Voz del Asistente
        if any(w in texto for w in ["mas lento", "habla mas lento", "despacio", "mas despacio"]):
            self.voz.cambiar_velocidad(-0.15)
            return

        if any(w in texto for w in ["mas rapido", "habla mas rapido"]):
            self.voz.cambiar_velocidad(+0.15)
            return

        if any(w in texto for w in ["cambiar voz", "otra voz", "voz masculina", "voz femenina", "voz grave", "voz aguda"]):
            self.voz.cambiar_tono()
            return

        # NODO 4: Navegación y Guiado Peatonal Asistido con Visión
        if any(w in texto for w in ["guiame", "guia", "llevame", "lleva", "ir a", "ir al", "ir a la", "como llego", "navegar", "buscar farmacia", "llegar a"]):
            lugar = texto_comando
            for prefijo in ["guiame a la", "guiame al", "guiame a", "guia a la", "guia a", "llevame a la", "llevame al", "llevame a", "lleva a", "ir a la", "ir al", "ir a", "como llego a la", "como llego al", "como llego a", "buscar", "navegar a", "llegar a una", "llegar a la", "llegar a"]:
                pref_norm = normalizar_texto(prefijo)
                if pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        lugar = texto_comando[idx + len(pref_norm):].strip()
                    break
            
            if not lugar:
                lugar = "farmacia"

            # Ceder la cámara al modo navegación asistida
            self.vision.detener_detector_gesto()
            self._camara_en_uso_por_comando = True

            self.btn_accion.text = "NAVEGANDO...\nTOCA PARA CANCELAR"
            self.btn_accion.background_color = (0.8, 0.2, 0.2, 1)

            self.voz.hablar(f"Buscando {lugar} más cercana y calculando ruta segura...")
            lat, lon = self.gps.obtener_coordenadas()
            mensaje_guia = self.gps.buscar_y_establecer_destino(lugar, lat, lon)
            self.lbl_estado.text = mensaje_guia
            self.voz.hablar(mensaje_guia)

            # Iniciar bucle de copiloto peatonal con cámara (cada 5.5 segundos)
            if self.evento_navegacion:
                self.evento_navegacion.cancel()
            self.evento_navegacion = Clock.schedule_interval(self._monitorear_navegacion_con_camara, 5.5)
            return

        # NODO 5: Cambiar Nombre de Activación
        if any(w in texto for w in ["cambiar nombre", "cambiar palabra", "llamate", "tu nombre es", "nuevo nombre", "llamarte"]):
            nuevo_nombre = texto_comando
            for prefijo in ["cambiar nombre a", "cambiar palabra a", "llamate a", "llamate", "tu nombre es", "nuevo nombre", "llamarte"]:
                pref_norm = normalizar_texto(prefijo)
                if pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        nuevo_nombre = texto_comando[idx + len(pref_norm):].strip()
                    break
            
            if nuevo_nombre:
                self.voz.actualizar_nombre_asistente(nuevo_nombre)
                self.lbl_estado.text = f"Nombre del asistente: {nuevo_nombre.capitalize()}"
            else:
                self.voz.hablar(f"No entendí el nuevo nombre. Mi nombre actual es {self.voz.nombre_asistente.capitalize()}.")
            return

        # NODO 6: Agenda Personal
        if any(w in texto for w in ["borrar agenda", "limpiar agenda", "borrar recordatorios", "limpiar recordatorios", "vaciar agenda"]):
            resumen = self.agenda.borrar_agenda()
            self.lbl_estado.text = "Agenda: Limpiada"
            self.voz.hablar(resumen)
            return

        menciona_agenda = any(w in texto for w in ["agenda", "recordatorio", "recordatorios", "tarea", "tareas", "nota"])
        quiere_guardar_agenda = (
            any(w in texto for w in ["anotar", "agendar", "recordar", "agregar recordatorio", "guardar nota"])
            or (menciona_agenda and any(w in texto for w in ["guardar", "agregar", "anotar", "agendar", "recordar", "nota"]))
        )
        if quiere_guardar_agenda:
            nota = texto_comando
            for prefijo in ["quiero guardar algo en mi agenda", "quiero guardar en mi agenda", "guardar algo en mi agenda", "guardar en mi agenda", "anotar", "agendar", "recordar que", "recordar", "guardar nota", "agregar recordatorio", "nota"]:
                pref_norm = normalizar_texto(prefijo)
                if pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        nota = texto_comando[idx + len(pref_norm):].strip()
                    break
            resumen = self.agenda.agregar_evento(nota if nota else texto_comando)
            self.lbl_estado.text = f"Agenda:\n{resumen}"
            self.voz.hablar(resumen)
            return

        if any(w in texto for w in ["ver agenda", "consultar agenda", "mi agenda", "mis recordatorios", "que tengo agendado", "mis tareas", "ver tareas", "que tengo en la agenda"]):
            resumen = self.agenda.consultar_agenda()
            self.lbl_estado.text = f"Agenda:\n{resumen}"
            self.voz.hablar(resumen)
            return

        # NODO 7: Lectura de Documentos, Hojas y Etiquetas
        if any(w in texto for w in ["leer", "lee", "lectura", "documento", "hoja", "etiqueta", "texto", "papel", "carta", "pagina", "revisa"]):
            self.vision.detener_detector_gesto()
            self._camara_en_uso_por_comando = True
            self.voz.hablar("Abriendo cámara para fotografiar y leer el documento.")
            self.lector.capturar_y_leer(self.al_completar_lectura_documento, ai_assistant=self.ai)
            return

        # NODO 8: Ubicación GPS actual
        if any(w in texto for w in ["ubicacion", "donde estoy", "donde me encuentro", "donde ando", "donde me ubico", "lugar", "donde", "direccion", "posicion"]) and not any(w in texto for w in ["guia", "llevame", "ir", "como llego"]):
            self.voz.hablar("Obteniendo tu ubicación actual.")
            lat, lon = self.gps.obtener_coordenadas()
            if lat is not None:
                direccion = self.gps.consultar_direccion_mapbox(lat, lon)
                self.lbl_estado.text = f"Ubicación:\n{direccion}"
                self.voz.hablar(f"Te encuentras en: {direccion}")
            else:
                self.voz.hablar("No se pudo obtener la señal GPS.")
                self.lbl_estado.text = "Error: GPS no disponible"
            return

        # NODO 9: Conexión Bastón ESP32 / Bluetooth
        if any(w in texto for w in ["conectar baston", "conectar", "conectate", "desconectar", "enlazar baston", "enlazar", "vincular baston", "vincular", "bluetooth", "baston"]) and not any(w in texto for w in ["guia", "llevame", "ir", "hola", "agenda", "dime", "donde"]):
            if "desconectar" in texto:
                self.bt.desconectar()
                self.lbl_estado.text = "Bastón desconectado."
                self.voz.hablar("Bastón desconectado.")
            else:
                self.lbl_estado.text = "Estado: Conectando al Bastón ESP32..."
                self.voz.hablar("Buscando señal del bastón. Conectando...")
                self.bt.conectar_async(self.al_completar_conexion_baston)
            return

        # NODO 10: Código QR
        if any(w in texto for w in ["qr", "comparte", "compartir", "codigo"]):
            ruta_qr = self.generar_qr_compartir()
            self.lbl_estado.text = "Código QR generado"
            if os.path.exists(ruta_qr):
                self.img_qr.source = ruta_qr
                self.img_qr.reload()
                self.img_qr.opacity = 1
                self.img_qr.height = dp(180)
            self.voz.hablar("Código QR generado en la pantalla para compartir la aplicación.")
            return

        # NODO 11: Análisis Visual Puntual (¿Qué tengo al frente?)
        if any(w in texto for w in [
            "frente", "al frente", "alfrente", "delante", "adelante", "enfrente", "que hay", "que veo", "que ves", "que miras",
            "que esta", "que tengo", "que hay al frente", "que tengo al frente", "que esta al frente", "mira", "mirar",
            "ver entorno", "ver camara", "ver foto", "camara", "foto", "obstaculo", "obstaculos", "objeto", "analizar"
        ]):
            self.vision.detener_detector_gesto()
            self._camara_en_uso_por_comando = True
            self.lbl_estado.text = "Tomando foto del frente..."
            self.voz.hablar("Tomando foto del frente.")
            self.vision.capturar_y_analizar(self.al_completar_analisis_vision, ai_assistant=self.ai)
            return

        # NODO 12: Configuración de Clave API
        quiere_guardar_api = any(w in texto for w in ["guardar clave", "guardar api key", "guardar clave api"])
        if not quiere_guardar_api and any(w in texto for w in ["configurar clave", "configurar api", "clave api", "api gemini"]):
            if self.ai.tiene_api_key_configurada():
                self.voz.hablar("La clave API de Gemini ya está configurada.")
            else:
                self.voz.hablar("Abriendo configuración. Pega una clave API de Google AI Studio.")
            if self.panel_api.opacity == 0:
                self.al_toggle_panel_api(None)
            return

        if quiere_guardar_api:
            nueva_key = texto_comando
            for pref in ["guardar clave api", "guardar clave", "guardar api key"]:
                pref_norm = normalizar_texto(pref)
                if pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        nueva_key = texto_comando[idx + len(pref_norm):].strip()
                    break
            if nueva_key:
                exito = self.ai.guardar_api_key(nueva_key)
                if exito:
                    self.lbl_estado.text = "Clave guardada. Probando conexión..."
                    self.voz.hablar("Clave guardada. Probando conexión con Gemini.")
                    self.ai.probar_conexion_gemini_async(self.al_resultado_prueba_api)
                else:
                    detalle = getattr(self.ai, 'ultimo_error_config', '') or "Verifica que sea una clave API válida."
                    self.lbl_estado.text = f"Error al guardar. {detalle}"
                    self.voz.hablar(detalle)
            return

        # NODO 12B: Configuración del Servidor de Voz Optimus Prime (XTTS)
        if any(w in texto for w in ["servidor voz", "ip servidor", "servidor optimus", "conectar servidor"]):
            palabras = texto_comando.split()
            posibles = [p for p in palabras if "." in p or "http" in p]
            if posibles:
                serv_url = posibles[-1].strip()
                if not serv_url.startswith("http"):
                    serv_url = f"http://{serv_url}:5000" if ":" not in serv_url else f"http://{serv_url}"
                self.voz.url_servidor_voz = serv_url
                self.voz._guardar_config()
                self.lbl_estado.text = f"Servidor Voz XTTS:\n{serv_url}"
                self.voz.hablar(f"Servidor de voz de Optimus actualizado.")
                return

        # NODO 13: Consultas Locales Offline (Hora, Fecha exacta, Ayuda)
        res_local = self.ai.responder_consulta_local(texto, texto_comando)
        if res_local:
            self.lbl_estado.text = res_local
            self.voz.hablar_respuesta_ia(res_local)
            return

        # NODO 14: IA Conversacional Gemini (Preguntas Libres y Fiestas con fecha real)
        self.lbl_estado.text = f"Consultando IA: {texto_comando}"
        self.voz.hablar("Pensando...")
        self.ai.consultar_gemini_async(texto_comando, self.al_recibir_respuesta_gemini)

    def al_recibir_respuesta_gemini(self, respuesta):
        self.lbl_estado.text = f"IA: {respuesta}"
        self.voz.hablar_respuesta_ia(respuesta)

    def _monitorear_navegacion_con_camara(self, dt):
        if not self.gps.navegacion_activa:
            if self.evento_navegacion:
                self.evento_navegacion.cancel()
                self.evento_navegacion = None
            self._camara_en_uso_por_comando = False
            self.programar_reinicio_control_por_gesto()
            return

        lat, lon = self.gps.obtener_coordenadas()
        instruccion_gps = self.gps.obtener_instruccion_guia(lat, lon)

        if not self.gps.navegacion_activa:
            # Llegó a destino
            if self.evento_navegacion:
                self.evento_navegacion.cancel()
                self.evento_navegacion = None
            self._camara_en_uso_por_comando = False
            self.btn_accion.text = "ESCUCHA ACTIVA\nHabla libremente"
            self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
            self.lbl_estado.text = instruccion_gps
            self.voz.hablar(instruccion_gps)
            self.programar_reinicio_control_por_gesto()
            return

        if self._analizando_camino:
            return

        self._analizando_camino = True

        def al_recibir_analisis_camino(info_camino):
            self._analizando_camino = False

            # Gesto de mano / palma frente a la cámara para cancelar navegación sin tocar la pantalla
            if info_camino and "GESTO_MANO_CANCELAR" in str(info_camino):
                print("[BastonApp] Navegación cancelada por gesto de mano frente a la cámara.")
                self.cancelar_navegacion_activa("por gesto de mano")
                return

            frase_combinada = f"{instruccion_gps}. {info_camino}".strip()

            if frase_combinada != self._ultima_frase_guia:
                self._ultima_frase_guia = frase_combinada
                self.lbl_estado.text = f"Guía:\n{frase_combinada}"
                self.voz.hablar(frase_combinada)

        self.vision.analizar_camino_en_navegacion(al_recibir_analisis_camino, ai_assistant=self.ai)

    def al_recibir_alerta_baston(self, mensaje_alerta):
        # Si el bastón físico envía orden de cancelar navegación
        if any(w in mensaje_alerta.upper() for w in ["CANCELAR", "BOTON_CANCELAR", "DETENER"]):
            if self.gps.navegacion_activa:
                self.cancelar_navegacion_activa("por botón del bastón")
                return

        Clock.schedule_once(lambda dt: self._actualizar_ui_alerta(mensaje_alerta), 0)

    def al_cambio_estado_baston(self, mensaje_estado):
        Clock.schedule_once(lambda dt: self._actualizar_estado_baston(mensaje_estado), 0)

    def _actualizar_estado_baston(self, mensaje_estado):
        self.lbl_estado.text = f"Estado: {mensaje_estado}"
        if "Reconectando" in mensaje_estado or "Reconectado" in mensaje_estado:
            self.voz.hablar(mensaje_estado)

    def al_completar_conexion_baston(self, exito):
        def actualizar_ui(dt):
            if exito:
                self.lbl_estado.text = "Estado: Conectado al Bastón ESP32"
                self.voz.hablar("Conectado.")
                self.bt.escuchar_alertas_baston(self.al_recibir_alerta_baston, self.al_cambio_estado_baston)
            else:
                detalle = self.bt.ultimo_error or "No se detectó el bastón."
                self.lbl_estado.text = detalle
                self.voz.hablar(detalle)
        Clock.schedule_once(actualizar_ui, 0)

    def _actualizar_ui_alerta(self, mensaje_alerta):
        self.lbl_estado.text = f"¡ALERTA!: {mensaje_alerta}"
        self.voz.hablar_alerta(mensaje_alerta)

    def al_completar_analisis_vision(self, resultado_texto):
        self._camara_en_uso_por_comando = False
        self.lbl_estado.text = f"Visión: {resultado_texto}"
        self.voz.hablar(resultado_texto)
        self.programar_reinicio_control_por_gesto()

    def al_completar_lectura_documento(self, texto_leido):
        self._camara_en_uso_por_comando = False
        self.lbl_estado.text = f"Lectura: {texto_leido}"
        self.voz.hablar(texto_leido)
        self.programar_reinicio_control_por_gesto()

    def generar_qr_compartir(self):
        if not qrcode:
            return ""
        url_repo = "https://github.com/Miguel-Quispe/bastonDesgraciado"
        img = qrcode.make(url_repo)
        ruta_salida = "qr_app.png"
        img.save(ruta_salida)
        return ruta_salida

    def on_stop(self):
        if self.evento_navegacion:
            self.evento_navegacion.cancel()
        if hasattr(self, 'voz'):
            self.voz.detener_escucha()
        if hasattr(self, 'bt'):
            self.bt.desconectar()
        if hasattr(self, 'vision'):
            self.vision.detener_detector_gesto()
        if self._wake_lock:
            try:
                if self._wake_lock.isHeld():
                    self._wake_lock.release()
            except Exception:
                pass

if __name__ == '__main__':
    BastonApp().run()
