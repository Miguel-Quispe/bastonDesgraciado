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
        if hasattr(self, 'user_data_dir') and self.user_data_dir:
            self.ai.actualizar_directorio_datos(self.user_data_dir)
        
        self.evento_navegacion = None
        self._analizando_camino = False
        self._ultima_frase_guia = ""
        self._ultima_distancia_anunciada = None
        self._wake_lock = None
        self._camara_en_uso_por_comando = False
        self._ultimo_toque_tiempo = 0

        # Vincular toque en cualquier parte de la pantalla para accesibilidad (cancelar ruta con toque)
        Window.bind(on_touch_down=self.al_tocar_pantalla)

        self.layout = BoxLayout(
            orientation='vertical',
            padding=[dp(16), dp(12), dp(16), dp(16)],
            spacing=dp(10)
        )

        # ── 1. BARRA SUPERIOR HUD (Estado en vivo y Acceso Rápido a Gemini) ──
        self.bar_superior = BoxLayout(
            orientation='horizontal',
            size_hint=(1, None),
            height=dp(42),
            spacing=dp(6)
        )

        self.lbl_baston = Label(
            text="BASTÓN OK" if (hasattr(self, 'bt') and self.bt.esta_conectado()) else "BASTÓN DESC.",
            font_size='13sp',
            bold=True,
            color=(1.0, 0.85, 0.0, 1) if (hasattr(self, 'bt') and self.bt.esta_conectado()) else (0.85, 0.3, 0.3, 1),
            size_hint=(0.38, 1),
            halign='left',
            valign='middle'
        )
        self.lbl_baston.bind(size=self.lbl_baston.setter('text_size'))
        self.bar_superior.add_widget(self.lbl_baston)

        self.lbl_gps = Label(
            text="GPS ACTIVO",
            font_size='12sp',
            bold=True,
            color=(0.2, 0.85, 0.5, 1),
            size_hint=(0.28, 1),
            halign='center',
            valign='middle'
        )
        self.lbl_gps.bind(size=self.lbl_gps.setter('text_size'))
        self.bar_superior.add_widget(self.lbl_gps)

        texto_api_btn = "🔑 Gemini OK" if self.ai.tiene_api_key_configurada() else "🔑 Config. API"
        self.btn_api_rapido = Button(
            text=texto_api_btn,
            font_size='12sp',
            bold=True,
            size_hint=(0.34, 1),
            background_normal='',
            background_color=(0.18, 0.35, 0.52, 1) if self.ai.tiene_api_key_configurada() else (0.8, 0.45, 0.1, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_api_rapido.bind(on_press=self.al_toggle_panel_api)
        self.bar_superior.add_widget(self.btn_api_rapido)

        self.layout.add_widget(self.bar_superior)

        # ── 2. VISOR CENTRAL HUD DE ALTO CONTRASTE (Marquesina Principal) ────
        self.lbl_estado = Label(
            text="Asistente de Autonomía\nEscucha activa",
            font_size='22sp',
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

        # ── 3. PANEL MODAL DE CONFIGURACIÓN API DE GEMINI (Oculto por defecto) ──
        self.panel_api = BoxLayout(
            orientation='vertical',
            spacing=dp(8),
            size_hint=(1, None),
            height=0,
            opacity=0
        )

        lbl_api_titulo = Label(
            text="Configurar Clave API de Gemini",
            font_size='17sp',
            bold=True,
            color=(1.0, 0.85, 0.1, 1),
            size_hint=(1, None),
            height=dp(28),
            halign='center'
        )
        lbl_api_titulo.bind(size=lbl_api_titulo.setter('text_size'))
        self.panel_api.add_widget(lbl_api_titulo)

        self.input_api_key = TextInput(
            text=self.ai.api_key or "",
            hint_text="Pega tu clave de Google AI Studio (AIzaSy...)",
            font_size='14sp',
            multiline=False,
            size_hint=(1, None),
            height=dp(48),
            background_color=(0.10, 0.14, 0.20, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(1.0, 0.85, 0.1, 1),
            padding=[dp(12), dp(12)]
        )
        self.panel_api.add_widget(self.input_api_key)

        fila_botones_api = BoxLayout(
            orientation='horizontal',
            spacing=dp(6),
            size_hint=(1, None),
            height=dp(46)
        )

        self.btn_pegar_api = Button(
            text="Pegar Portapapeles",
            font_size='14sp',
            bold=True,
            size_hint=(0.5, 1),
            background_normal='',
            background_color=(0.15, 0.55, 0.45, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_pegar_api.bind(on_press=self.al_pegar_api_key_clipboard)
        fila_botones_api.add_widget(self.btn_pegar_api)

        self.btn_guardar_api = Button(
            text="Guardar y Probar",
            font_size='14sp',
            bold=True,
            size_hint=(0.5, 1),
            background_normal='',
            background_color=(0.1, 0.5, 0.85, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_guardar_api.bind(on_press=self.al_guardar_api_key_ui)
        fila_botones_api.add_widget(self.btn_guardar_api)
        self.panel_api.add_widget(fila_botones_api)

        self.btn_cerrar_api = Button(
            text="Cerrar Configuración",
            font_size='14sp',
            bold=True,
            size_hint=(1, None),
            height=dp(38),
            background_normal='',
            background_color=(0.35, 0.15, 0.15, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_cerrar_api.bind(on_press=self.al_toggle_panel_api)
        self.panel_api.add_widget(self.btn_cerrar_api)

        self.layout.add_widget(self.panel_api)

        # ── 4. BOTÓN GIGANTE ACCESIBLE DE ESCUCHA (125dp Altura) ─────────────
        self.btn_accion = Button(
            text="ESCUCHA ACTIVA\nToca o muestra tu palma",
            font_size='20sp',
            bold=True,
            size_hint=(1, None),
            height=dp(125),
            background_normal='',
            background_color=(0.08, 0.65, 0.42, 1),
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
        self.voz.detener_voz()
        self.emitir_vibracion_bienvenida()

        if "gesto" in motivo or "palma" in motivo:
            print("[BastonApp] Navegación cancelada por gesto de palma. Preguntando nuevo comando...")
            self.lbl_estado.text = "Ruta cancelada por palma.\n¿Cuál es tu comando?"
            self.btn_accion.text = "PALMA DETECTADA\nAbriendo micrófono..."
            self.btn_accion.background_color = (0.8, 0.5, 0.1, 1)
            self.btn_accion.color = (0, 0, 0, 1)
            # Abrir el micrófono de inmediato para recibir la nueva orden del usuario
            Clock.schedule_once(lambda dt: self._abrir_comando_por_gesto(), 0.15)
        else:
            self.lbl_estado.text = "Navegación cancelada."
            self.btn_accion.text = "ESCUCHA ACTIVA\nHabla libremente"
            self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
            self.btn_accion.color = (1, 1, 1, 1)
            self.voz.hablar("Navegación y copiloto visual cancelados.")
            self.programar_reinicio_control_por_gesto(0.2)

    def al_toggle_panel_api(self, instance):
        if self.panel_api.opacity == 0:
            clave_actual = self.ai.api_key or ""
            self.input_api_key.text = clave_actual
            self.panel_api.height = dp(180)
            self.panel_api.opacity = 1
            self.btn_api_rapido.text = "Cerrar ✕"
            self.btn_api_rapido.background_color = (0.55, 0.2, 0.2, 1)
            self.lbl_estado.size_hint = (1, 0.4)
        else:
            self.panel_api.height = 0
            self.panel_api.opacity = 0
            self.lbl_estado.size_hint = (1, 1)
            texto_api_btn = "🔑 Gemini OK" if self.ai.tiene_api_key_configurada() else "🔑 Config. API"
            self.btn_api_rapido.text = texto_api_btn
            self.btn_api_rapido.background_color = (0.18, 0.35, 0.52, 1) if self.ai.tiene_api_key_configurada() else (0.8, 0.45, 0.1, 1)

    def al_pegar_api_key_clipboard(self, instance):
        try:
            from kivy.core.clipboard import Clipboard
            texto = Clipboard.paste()
            if texto and texto.strip():
                self.input_api_key.text = texto.strip()
                self.lbl_estado.text = "Clave pegada. Presiona 'Guardar y Probar'."
                self.voz.hablar("Clave pegada del portapapeles. Presiona guardar y probar.")
            else:
                self.lbl_estado.text = "El portapapeles está vacío. Copia tu clave primero."
                self.voz.hablar("El portapapeles está vacío. Copia la clave primero.")
        except Exception as e:
            self.lbl_estado.text = f"Error al acceder al portapapeles: {e}"

    def al_guardar_api_key_ui(self, instance):
        nueva_key = self.input_api_key.text.strip()
        if not nueva_key:
            self.lbl_estado.text = "Escribe o pega la clave API antes de guardar."
            self.voz.hablar("Escribe o pega la clave antes de guardar.")
            return

        exito = self.ai.guardar_api_key(nueva_key)
        if exito:
            self.lbl_estado.text = "Clave guardada exitosamente. Probando conexión ultrarrápida con Gemini..."
            self.voz.hablar("Clave guardada. Probando conexión con Gemini.")
            self.ai.probar_conexion_gemini_async(self.al_resultado_prueba_api)
        else:
            detalle = getattr(self.ai, 'ultimo_error_config', '') or "Verifica que sea una clave válida."
            self.lbl_estado.text = f"Error al guardar la clave: {detalle}"
            self.voz.hablar(detalle)

    def al_resultado_prueba_api(self, exito, mensaje):
        if exito:
            self.lbl_estado.text = "Clave API de Gemini conectada correctamente."
            self.btn_api_rapido.text = "🔑 Gemini OK"
            self.btn_api_rapido.background_color = (0.18, 0.35, 0.52, 1)
            self.voz.hablar(mensaje)
            if self.panel_api.opacity != 0:
                Clock.schedule_once(lambda dt: self.al_toggle_panel_api(None), 1.5)
        else:
            self.lbl_estado.text = f"Gemini: {mensaje}"
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
        self.btn_accion.text = "ESCUCHA ACTIVA\nHabla libremente"
        self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
        self.btn_accion.color = (1, 1, 1, 1)

    def iniciar_control_por_gesto(self):
        if not self.voz.activity or self._camara_en_uso_por_comando or self.gps.navegacion_activa:
            return
        iniciado = self.vision.iniciar_detector_gesto(self.activar_comando_por_gesto)
        if iniciado:
            self.lbl_estado.text = "Cámara trasera activa. Muestra la palma abierta para dar un comando."
            self.btn_accion.text = "ESCUCHA ACTIVA\nHabla libremente"
            self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
            self.btn_accion.color = (1, 1, 1, 1)
        else:
            self.lbl_estado.text = "Asistente listo. Presiona el botón para dar una orden."
            self.btn_accion.text = "ESCUCHA ACTIVA\nHabla libremente"
            self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
            self.btn_accion.color = (1, 1, 1, 1)

    def activar_comando_por_gesto(self):
        """
        Se activa al ver la palma abierta:
        - Si la navegación a la farmacia u otro destino está activa, se cancela y abre el micrófono de inmediato.
        - Si el asistente estaba respondiendo o hablando, detiene de inmediato la consulta previa.
        - Pausa la cámara y abre el micrófono de inmediato para escuchar la nueva orden.
        """
        try:
            print("[BastonApp] ¡Palma detectada!")
            # Detiene en seco la voz/consulta actual si estaba hablando
            self.voz.detener_voz()

            if self.gps.navegacion_activa:
                print("[BastonApp] Cancelando navegación activa por gesto de palma detectado.")
                self.cancelar_navegacion_activa("por gesto de palma")
                return

            self.lbl_estado.text = "¡Palma detectada! Abriendo micrófono..."
            self.btn_accion.text = "PALMA DETECTADA\nAbriendo micrófono..."
            self.btn_accion.background_color = (0.8, 0.5, 0.1, 1)
            self.btn_accion.color = (0, 0, 0, 1)
            self.vision.pausar_detector_gesto()
            Clock.schedule_once(lambda dt: self._abrir_comando_por_gesto(), 0.10)
        except Exception as e:
            print(f"[BastonApp] Error en activar_comando_por_gesto: {e}")

    def _abrir_comando_por_gesto(self):
        def _al_finalizar_escucha():
            # Si el micrófono se cierra y no estamos en navegación o foto exclusiva, reanudar cámara
            if not self._camara_en_uso_por_comando and not self.gps.navegacion_activa:
                self.programar_reinicio_control_por_gesto(0.1)

        try:
            self.voz.detener_voz()
            if self.voz.escuchar_una_vez(self.procesar_comando_texto, _al_finalizar_escucha, self.al_recibir_parcial):
                self.lbl_estado.text = "Micrófono activo. Di tu comando ahora..."
                self.btn_accion.text = "MICRÓFONO ACTIVO\nTe escucho, ¿cuál es tu comando?"
                self.btn_accion.background_color = (0.85, 0.2, 0.2, 1)
                self.btn_accion.color = (1, 1, 1, 1)
                self.emitir_vibracion_bienvenida()
            else:
                self.lbl_estado.text = "Micrófono no disponible. Muestra la palma de nuevo."
                Clock.schedule_once(lambda dt: self.vision.reanudar_detector_gesto(self.activar_comando_por_gesto), 1.0)
        except Exception as e:
            print(f"[BastonApp] Error en _abrir_comando_por_gesto: {e}")
            Clock.schedule_once(lambda dt: self.vision.reanudar_detector_gesto(self.activar_comando_por_gesto), 1.0)

    def programar_reinicio_control_por_gesto(self, demora=0.1):
        Clock.schedule_once(lambda dt: self._reanudar_control_por_gesto_si_libre(), demora)

    def _reanudar_control_por_gesto_si_libre(self):
        if self._camara_en_uso_por_comando or self.gps.navegacion_activa:
            return

        # La cámara se reenciende de inmediato y vigila la palma abierta mientras el asistente responde
        self.vision.reanudar_detector_gesto(self.activar_comando_por_gesto)

        self.btn_accion.text = "ESCUCHA ACTIVA\nHabla libremente"
        self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
        self.btn_accion.color = (1, 1, 1, 1)

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

        elif request_code == 1002:
            self._camara_en_uso_por_comando = False
            if hasattr(self, 'vision'):
                self.vision._esperando_resultado_intent = False
                self.vision._captura_en_progreso = False
                Clock.unschedule(self.vision._timeout_intent_camara)
            if result_code == -1:
                self.lbl_estado.text = "Foto tomada. Procesando visión..."
                Clock.schedule_once(lambda dt: self.vision.procesar_foto_capturada(), 0.1)
            else:
                self.vision.cancelar_captura("Captura de foto cancelada.")
                self.programar_reinicio_control_por_gesto(0.2)

        elif request_code == 1003:
            if hasattr(self, 'lector'):
                self.lector._esperando_resultado_intent = False
                self.lector._captura_en_progreso = False
            if result_code == -1:
                self._camara_en_uso_por_comando = True
                self.lbl_estado.text = "Foto tomada. Leyendo documento..."
                Clock.schedule_once(lambda dt: self.lector.procesar_foto_capturada(intent_data=intent_data), 0.1)
            else:
                self._camara_en_uso_por_comando = False
                self.lector.cancelar_captura("Lectura de documento cancelada.")
                self.programar_reinicio_control_por_gesto(0.2)

    def al_presionar_boton_escucha(self, instance):
        if self.gps.navegacion_activa:
            self.cancelar_navegacion_activa("por botón táctil")
            return

        self.vision.pausar_detector_gesto()
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

        # Paso 4: A menos que el comando requiera uso exclusivo de la cámara (fotos o guiado peatonal),
        # reencendemos la cámara de inmediato para que vigile la mano del usuario mientras el asistente responde.
        es_comando_foto_o_nav = any(w in texto for w in [
            "guiame", "guia", "llevame", "lleva", "ir a", "como llego", "navegar",
            "leer", "lee", "lectura", "documento",
            "frente", "al frente", "delante", "que hay", "que veo", "que ves", "foto", "obstaculo"
        ])
        if not es_comando_foto_o_nav:
            self.programar_reinicio_control_por_gesto(0.1)

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
        if any(w in texto for w in ["guiame", "guia", "llevame", "lleva", "ir a", "ir al", "ir a la", "como llego", "navegar", "buscar farmacia", "llegar a", "farmacia"]):
            lugar = texto_comando
            for prefijo in [
                "llevame a la farmacia mas cercana", "llevame a la farmacia mas cercano",
                "guiame a la farmacia mas cercana", "guiame a la farmacia mas cercano",
                "llevame a la farmacia", "guiame a la farmacia", "lleva a la farmacia",
                "guiame a la", "guiame al", "guiame a", "guia a la", "guia a",
                "llevame a la", "llevame al", "llevame a", "lleva a", "ir a la", "ir al", "ir a",
                "como llego a la", "como llego al", "como llego a", "buscar", "navegar a", "llegar a una", "llegar a la", "llegar a"
            ]:
                pref_norm = normalizar_texto(prefijo)
                if pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        lugar = texto_comando[idx + len(pref_norm):].strip()
                    break

            # Limpiar sufijos o asumir farmacia si se mencionó
            lugar_norm = normalizar_texto(lugar)
            for sufijo in ["mas cercana", "mas cercano", "cercana", "cercano"]:
                if lugar_norm.endswith(sufijo):
                    lugar = lugar[:len(lugar) - len(sufijo)].strip()
                    lugar_norm = normalizar_texto(lugar)

            if not lugar or "farmacia" in texto:
                lugar = "farmacia"

            # Iniciar navegación con copiloto visual
            self._camara_en_uso_por_comando = True

            self.btn_accion.text = "NAVEGANDO A DESTINO\n(MUESTRA LA PALMA PARA CANCELAR)"
            self.btn_accion.background_color = (0.8, 0.2, 0.2, 1)
            self.btn_accion.color = (1, 1, 1, 1)

            self.voz.hablar(f"Calculando ruta a {lugar} más cercana y activando cámara...")
            lat, lon = self.gps.obtener_coordenadas()
            mensaje_guia = self.gps.buscar_y_establecer_destino(lugar, lat, lon)
            self._ultima_distancia_anunciada = getattr(self.gps, 'ultima_distancia', None)
            self.lbl_estado.text = mensaje_guia
            self.voz.hablar(mensaje_guia)

            # Iniciar bucle de copiloto peatonal con cámara permanente (cada 4.0 segundos)
            if self.evento_navegacion:
                self.evento_navegacion.cancel()
            self.evento_navegacion = Clock.schedule_interval(self._monitorear_navegacion_con_camara, 4.0)
            return

        # NODO 5: Cambiar Nombre de Activación
        palabras_cambiar_nombre = [
            "cambiar nombre", "cambia nombre", "cambiar el nombre", "cambia el nombre",
            "cambiar de nombre", "cambia de nombre", "cambiar tu nombre", "cambia tu nombre",
            "tu nombre es", "tu nombre sera", "ahora te llamas", "te llamas",
            "llamate", "llamarte", "nuevo nombre", "ponte de nombre", "ponte el nombre"
        ]
        if any(w in texto for w in palabras_cambiar_nombre):
            nuevo_nombre = texto_comando
            for prefijo in [
                "cambiar nombre a", "cambia nombre a", "cambia el nombre a", "cambiar el nombre a",
                "cambia tu nombre a", "cambiar tu nombre a", "cambia de nombre a", "cambiar de nombre a",
                "tu nombre es", "tu nombre sera", "ahora te llamas", "te llamas",
                "nuevo nombre a", "nuevo nombre es", "nuevo nombre",
                "llamate a", "llamate", "llamarte a", "llamarte",
                "ponte de nombre", "ponte el nombre", "cambiar nombre", "cambia nombre"
            ]:
                pref_norm = normalizar_texto(prefijo)
                if pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        nuevo_nombre = texto_comando[idx + len(pref_norm):].strip(" :.,-")
                    break

            if nuevo_nombre.lower().startswith("a "):
                nuevo_nombre = nuevo_nombre[2:].strip()
            elif nuevo_nombre.lower().startswith("de "):
                nuevo_nombre = nuevo_nombre[3:].strip()

            partes = nuevo_nombre.strip().split()
            if partes:
                nuevo_nombre = partes[0].strip(" :.,-")
            
            if nuevo_nombre:
                self.voz.actualizar_nombre_asistente(nuevo_nombre)
                self.lbl_estado.text = f"Nombre del asistente:\n{nuevo_nombre.capitalize()}"
                self.voz.hablar(f"Entendido. Mi nombre ahora es {nuevo_nombre.capitalize()}. ¡Listo para ayudarte!", perfil="animada")
            else:
                self.voz.hablar(f"No entendí el nuevo nombre. Mi nombre actual es {self.voz.nombre_asistente.capitalize()}.")
            self.programar_reinicio_control_por_gesto(0.2)
            return

        # NODO 6: Agenda Personal
        if any(w in texto for w in ["borrar agenda", "limpiar agenda", "borrar recordatorios", "limpiar recordatorios", "vaciar agenda"]):
            resumen = self.agenda.borrar_agenda()
            self.lbl_estado.text = "Agenda: Limpiada"
            self.voz.hablar(resumen)
            self.programar_reinicio_control_por_gesto(0.2)
            return

        if any(w in texto for w in ["ver agenda", "consultar agenda", "mi agenda", "mis recordatorios", "que tengo agendado", "mis tareas", "ver tareas", "que tengo en la agenda", "revisar agenda"]):
            resumen = self.agenda.consultar_agenda()
            self.lbl_estado.text = f"Agenda:\n{resumen}"
            self.voz.hablar(resumen)
            self.programar_reinicio_control_por_gesto(0.2)
            return

        menciona_guardar = any(w in texto for w in [
            "guardar", "guarda", "agendar", "agenda", "anotar", "anota",
            "recordar", "recuerda", "recordatorio", "recordatorios", "agregar", "agrega"
        ])
        tiene_fecha_o_agenda = any(w in texto for w in [
            "hasta", "el dia", "fecha", "agenda", "recordatorio", "tarea", "medicina", "cita"
        ])

        if menciona_guardar and (tiene_fecha_o_agenda or "hasta" in texto or texto.startswith("guardar") or texto.startswith("agendar") or texto.startswith("anotar")):
            nota = texto_comando
            for prefijo in [
                "quiero guardar algo en mi agenda", "quiero guardar en mi agenda",
                "guardar algo en mi agenda", "guardar en mi agenda", "guardar en la agenda",
                "agregar a mi agenda", "agregar en mi agenda", "agregar recordatorio",
                "guardar nota", "guardar recordatorio", "guardar tarea",
                "guardar", "guarda", "anotar", "anota", "agendar", "agenda",
                "recordar que", "recordar", "recuerda que", "recuerda", "agregar", "agrega"
            ]:
                pref_norm = normalizar_texto(prefijo)
                if texto.startswith(pref_norm + " ") or pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        nota = texto_comando[idx + len(pref_norm):].strip(" :.,-")
                    break
            resumen = self.agenda.agregar_evento(nota if nota else texto_comando)
            self.lbl_estado.text = f"Agenda:\n{resumen}"
            self.voz.hablar(resumen)
            self.programar_reinicio_control_por_gesto(0.2)
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
            self.programar_reinicio_control_por_gesto(0.2)
            return

        # NODO 9: Conexión Bastón ESP32 / Bluetooth
        if any(w in texto for w in [
            "desconectar", "desconectate", "desconecta", "desconectate del baston", "desconecta el baston",
            "desvincular", "desvincula", "desenlazar", "desenlaza", "apagar baston",
            "conectar baston", "conectar", "conectate", "conectate con el baston", "conectate al baston",
            "enlazar baston", "enlazar", "vincular baston", "vincular", "bluetooth", "baston"
        ]) and not any(w in texto for w in ["guia", "llevame", "ir", "hola", "agenda", "dime", "donde"]):
            es_desconectar = any(w in texto for w in ["desconectar", "desconectate", "desconecta", "desvincular", "desvincula", "desenlazar", "desenlaza", "apagar", "cortar"])
            if es_desconectar:
                self.bt.desconectar()
                self.lbl_estado.text = "Bastón desconectado."
                if hasattr(self, 'lbl_baston'):
                    self.lbl_baston.text = "BASTÓN DESC."
                    self.lbl_baston.color = (0.85, 0.3, 0.3, 1)
                self.voz.hablar("Bastón desconectado.")
                self.programar_reinicio_control_por_gesto(0.2)
            else:
                self.lbl_estado.text = "Estado: Conectando al Bastón ESP32..."
                self.voz.hablar("Buscando señal del bastón. Conectando...")
                self.bt.conectar_async(self.al_completar_conexion_baston)
            return

        # NODO 10: Código QR
        if any(w in texto for w in ["qr", "comparte", "compartir", "codigo qr", "codigo", "mostrar qr"]):
            ruta_qr = self.generar_qr_compartir()
            self.lbl_estado.text = "Código QR generado en pantalla.\nEscanea para compartir la aplicación."
            if ruta_qr and os.path.exists(ruta_qr):
                self.img_qr.source = ruta_qr
                self.img_qr.reload()
                self.img_qr.opacity = 1
                self.img_qr.height = dp(240)
            self.voz.hablar("Código QR generado en la pantalla para compartir la aplicación.")
            self.programar_reinicio_control_por_gesto(0.2)
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
            self.programar_reinicio_control_por_gesto(0.2)
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
            self.programar_reinicio_control_por_gesto(0.2)
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
                self.programar_reinicio_control_por_gesto(0.2)
                return

        # NODO 13: Consultas Locales Offline (Hora, Fecha exacta, Ayuda)
        res_local = self.ai.responder_consulta_local(texto, texto_comando)
        if res_local:
            self.lbl_estado.text = res_local
            self.voz.hablar_respuesta_ia(res_local)
            self.programar_reinicio_control_por_gesto(0.2)
            return

        # NODO 14: IA Conversacional Gemini (Preguntas Libres y Fiestas con fecha real)
        self.lbl_estado.text = f"Consultando IA: {texto_comando}"
        self.voz.hablar("Pensando...")
        self.ai.consultar_gemini_async(texto_comando, self.al_recibir_respuesta_gemini)

    def al_recibir_respuesta_gemini(self, respuesta):
        self.lbl_estado.text = f"IA: {respuesta}"
        self.programar_reinicio_control_por_gesto(0.1)
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

            obstaculo_real = ""
            if info_camino and "despejado" not in str(info_camino).lower():
                obstaculo_real = str(info_camino).strip()

            dist_actual = getattr(self.gps, 'ultima_distancia', None)
            hubo_avance = (
                self._ultima_distancia_anunciada is None or 
                (dist_actual is not None and abs(dist_actual - self._ultima_distancia_anunciada) >= 8)
            )

            if obstaculo_real:
                self.lbl_estado.text = f"Guía:\n{instruccion_gps}\n{obstaculo_real}"
                self.voz.hablar(f"Atención: {obstaculo_real}")
            elif hubo_avance:
                self._ultima_distancia_anunciada = dist_actual
                self.lbl_estado.text = f"Guía:\n{instruccion_gps}"
                self.voz.hablar(instruccion_gps)

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
        if hasattr(self, 'lbl_baston'):
            if "Conectado" in mensaje_estado:
                self.lbl_baston.text = "BASTÓN OK"
                self.lbl_baston.color = (1.0, 0.85, 0.0, 1)
            else:
                self.lbl_baston.text = "BASTÓN DESC."
                self.lbl_baston.color = (0.8, 0.3, 0.3, 1)
        if "Reconectando" in mensaje_estado or "Reconectado" in mensaje_estado:
            self.voz.hablar(mensaje_estado)

    def al_completar_conexion_baston(self, exito):
        def actualizar_ui(dt):
            if hasattr(self, 'lbl_baston'):
                if exito:
                    self.lbl_baston.text = "BASTÓN OK"
                    self.lbl_baston.color = (1.0, 0.85, 0.0, 1)
                else:
                    self.lbl_baston.text = "BASTÓN DESC."
                    self.lbl_baston.color = (0.8, 0.3, 0.3, 1)
            if exito:
                self.lbl_estado.text = "Estado: Conectado al Bastón ESP32"
                self.voz.hablar("Conectado.")
                self.bt.escuchar_alertas_baston(self.al_recibir_alerta_baston, self.al_cambio_estado_baston)
            else:
                detalle = self.bt.ultimo_error or "No se detectó el bastón."
                self.lbl_estado.text = detalle
                self.voz.hablar(detalle)
            # Reanudar inmediatamente la detección de mano para que el usuario pueda volver a dar órdenes
            self.programar_reinicio_control_por_gesto()
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
        self.lbl_estado.text = f"Lectura:\n{texto_leido}"
        if hasattr(self.voz, 'hablar_respuesta_ia'):
            self.voz.hablar_respuesta_ia(texto_leido)
        else:
            self.voz.hablar(texto_leido)
        self.programar_reinicio_control_por_gesto(0.2)

    def generar_qr_compartir(self):
        url_repo = "https://github.com/Miguel-Quispe/bastonDesgraciado"
        directorio = getattr(self, 'user_data_dir', None) or os.getcwd()
        try:
            os.makedirs(directorio, exist_ok=True)
        except Exception:
            directorio = os.getcwd()
        ruta_salida = os.path.join(directorio, "qr_app.png")

        # Opción 1: Librería qrcode
        if qrcode:
            try:
                img = qrcode.make(url_repo)
                img.save(ruta_salida)
                if os.path.exists(ruta_salida) and os.path.getsize(ruta_salida) > 0:
                    return ruta_salida
            except Exception as e:
                print(f"[BastonApp] Error generando QR con librería qrcode: {e}")

        # Opción 2: Descargar imagen QR desde servicio público si hay conexión
        try:
            import requests
            api_qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={url_repo}"
            resp = requests.get(api_qr_url, timeout=3)
            if resp.status_code == 200:
                with open(ruta_salida, "wb") as f:
                    f.write(resp.content)
                if os.path.exists(ruta_salida) and os.path.getsize(ruta_salida) > 0:
                    return ruta_salida
        except Exception as e:
            print(f"[BastonApp] Error descargando QR de red: {e}")

        # Opción 3: Generación visual de respaldo con Pillow
        try:
            from PIL import Image as PILImage, ImageDraw
            img = PILImage.new("RGB", (280, 280), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 10, 270, 270], outline=(0, 0, 0), width=5)
            draw.rectangle([30, 30, 100, 100], fill=(0, 0, 0))
            draw.rectangle([180, 30, 250, 100], fill=(0, 0, 0))
            draw.rectangle([30, 180, 100, 250], fill=(0, 0, 0))
            draw.rectangle([130, 130, 160, 160], fill=(0, 0, 0))
            img.save(ruta_salida)
            return ruta_salida
        except Exception as e:
            print(f"[BastonApp] Error en generador QR con PIL: {e}")

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
