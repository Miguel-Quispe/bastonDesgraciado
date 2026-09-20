import os
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

from modules.bluetooth_manager import BluetoothManager
from modules.speech_engine import SpeechEngine, normalizar_texto
from modules.location_service import LocationService
from modules.vision_analyzer import VisionAnalyzer
from modules.agenda_manager import AgendaManager
from modules.document_reader import DocumentReader
from modules.ai_assistant import AIAssistant

class BastonApp(App):
    def build(self):
        self.title = "Bastón Inteligente - Asistente Autónomo"
        # Ajuste visual para accesibilidad de alto contraste
        Window.clearcolor = (0.05, 0.08, 0.12, 1)

        self.bt = BluetoothManager()
        self.voz = SpeechEngine()
        self.gps = LocationService()
        self.vision = VisionAnalyzer()
        self.agenda = AgendaManager()
        self.lector = DocumentReader()
        self.ai = AIAssistant()
        self.evento_navegacion = None

        self.layout = BoxLayout(orientation='vertical', padding=25, spacing=20)

        # ── Etiqueta de estado principal ──────────────────────────────────────
        self.lbl_estado = Label(
            text="Asistente de Autonomía\nEscucha activa. Habla directamente o di 'Bastón'.",
            font_size='22sp',
            bold=True,
            color=(1, 1, 1, 1),
            halign='center',
            valign='middle',
            size_hint=(1, 0.25)
        )
        self.lbl_estado.bind(size=self.lbl_estado.setter('text_size'))
        self.layout.add_widget(self.lbl_estado)

        self.img_qr = Image(
            size_hint=(1, 0.25),
            opacity=0
        )
        self.layout.add_widget(self.img_qr)

        # ── Panel de configuración de clave API (oculto por defecto) ──────────
        self.panel_api = BoxLayout(
            orientation='vertical',
            spacing=8,
            size_hint=(1, None),
            height=0,
            opacity=0
        )

        lbl_api_titulo = Label(
            text="🔑 Clave API de Gemini",
            font_size='18sp',
            bold=True,
            color=(0.9, 0.8, 0.2, 1),
            size_hint=(1, None),
            height=36,
            halign='center'
        )
        lbl_api_titulo.bind(size=lbl_api_titulo.setter('text_size'))
        self.panel_api.add_widget(lbl_api_titulo)

        self.input_api_key = TextInput(
            hint_text="Pega aquí tu clave API de Gemini...",
            font_size='16sp',
            multiline=False,
            size_hint=(1, None),
            height=52,
            background_color=(0.12, 0.16, 0.22, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.9, 0.8, 0.2, 1),
            padding=[12, 14]
        )
        self.panel_api.add_widget(self.input_api_key)

        self.btn_guardar_api = Button(
            text="💾 Guardar Clave API",
            font_size='18sp',
            bold=True,
            size_hint=(1, None),
            height=52,
            background_normal='',
            background_color=(0.1, 0.5, 0.85, 1),
            color=(1, 1, 1, 1)
        )
        self.btn_guardar_api.bind(on_press=self.al_guardar_api_key_ui)
        self.panel_api.add_widget(self.btn_guardar_api)

        self.layout.add_widget(self.panel_api)

        # ── Botón de configuración (engranaje) ────────────────────────────────
        self.btn_config = Button(
            text="⚙ Configurar Clave API",
            font_size='16sp',
            size_hint=(1, None),
            height=44,
            background_normal='',
            background_color=(0.18, 0.22, 0.30, 1),
            color=(0.7, 0.7, 0.7, 1)
        )
        self.btn_config.bind(on_press=self.al_toggle_panel_api)
        self.layout.add_widget(self.btn_config)

        # ── Botón principal de escucha ────────────────────────────────────────
        self.btn_accion = Button(
            text="🎤 ESCUCHA ACTIVA\n(Toca para hablar)",
            font_size='22sp',
            bold=True,
            size_hint=(1, 0.30),
            background_normal='',
            background_color=(0.1, 0.65, 0.45, 1),
            color=(1, 1, 1, 1),
            halign='center'
        )
        self.btn_accion.bind(on_press=self.al_presionar_boton_escucha)
        self.layout.add_widget(self.btn_accion)

        return self.layout

    def al_toggle_panel_api(self, instance):
        """Muestra u oculta el panel de configuración de la clave API."""
        if self.panel_api.opacity == 0:
            # Mostrar panel: cargar la clave actual si existe
            clave_actual = self.ai.api_key or ""
            self.input_api_key.text = clave_actual
            self.panel_api.height = 160
            self.panel_api.opacity = 1
            self.btn_config.text = "✖ Cerrar Configuración"
            self.btn_config.background_color = (0.45, 0.1, 0.1, 1)
        else:
            # Ocultar panel
            self.panel_api.height = 0
            self.panel_api.opacity = 0
            self.btn_config.text = "⚙ Configurar Clave API"
            self.btn_config.background_color = (0.18, 0.22, 0.30, 1)

    def al_guardar_api_key_ui(self, instance):
        """Guarda la clave API escrita en el TextInput."""
        nueva_key = self.input_api_key.text.strip()
        if not nueva_key:
            self.lbl_estado.text = "⚠ Escribe la clave API antes de guardar."
            return

        exito = self.ai.guardar_api_key(nueva_key)
        if exito:
            self.lbl_estado.text = "✅ Clave API de Gemini guardada correctamente."
            self.voz.hablar("Clave API de Gemini guardada. El asistente ya puede responder preguntas.")
            # Cerrar el panel automáticamente
            self.al_toggle_panel_api(None)
        else:
            self.lbl_estado.text = "❌ Error al guardar la clave. Verifica el almacenamiento."
            self.voz.hablar("Ocurrió un error al guardar la clave.")



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
            request_permissions(permisos)
        except Exception as e:
            print(f"[BastonApp] Permisos nativos no aplicados: {e}")

    def emitir_vibracion_bienvenida(self):
        """Emite una vibración háptica al abrir la app para confirmación táctil del usuario no vidente."""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            activity = PythonActivity.mActivity
            vibrator = activity.getSystemService(Context.VIBRATOR_SERVICE)
            if vibrator:
                vibrator.vibrate(300)
        except Exception as e:
            print(f"[BastonApp] Vibración no disponible: {e}")

    def on_start(self):
        """Inicia los servicios automáticos y emite aviso táctil y auditivo para personas no videntes."""
        self.solicitar_permisos_android()
        self.emitir_vibracion_bienvenida()

        try:
            from android import activity
            activity.bind(on_activity_result=self.al_recibir_resultado_actividad)
        except Exception as e:
            print(f"[BastonApp] Fallback vinculo actividad: {e}")

        nombre_actual = self.voz.nombre_asistente.capitalize()
        mensaje_bienvenida = f"Aplicación iniciada. Asistente activo con el nombre {nombre_actual}. Te escucho. Puedes decir tu comando directamente."
        
        try:
            self.voz.hablar(mensaje_bienvenida)
        except Exception as e:
            print(f"[BastonApp] Error en bienvenida por voz: {e}")

        try:
            self.voz.iniciar_escucha_continua(
                callback_comando=self.procesar_comando_texto,
                callback_parcial=self.al_recibir_parcial
            )
        except Exception as e:
            print(f"[BastonApp] Error iniciando escucha continua: {e}")

        # Intentar conectar automáticamente al Bastón ESP32 al iniciar la app
        try:
            self.bt.conectar_async(self.al_completar_conexion_baston)
        except Exception as e:
            print(f"[BastonApp] Error iniciando conexión Bluetooth automática: {e}")

    def al_recibir_resultado_actividad(self, request_code, result_code, intent_data):
        """Recibe el resultado del micrófono nativo de Android por Intent."""
        if request_code == 1001 and result_code == -1 and intent_data:
            try:
                from jnius import autoclass
                RecognizerIntent = autoclass('android.speech.RecognizerIntent')
                matches = intent_data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                if matches and matches.size() > 0:
                    texto = str(matches.get(0)).strip()
                    print(f"[BastonApp Speech Intent Result]: {texto}")
                    self.lbl_estado.text = f"Escuchado: {texto}"
                    self.voz._procesar_texto_reconocido(texto, self.procesar_comando_texto)
            except Exception as e:
                print(f"[BastonApp Error Intent Result]: {e}")

    def al_presionar_boton_escucha(self, instance):
        """Activa el micrófono nativo de Android inmediatamente al tocar el botón."""
        self.voz.solicitar_voz_android()

    def al_recibir_parcial(self, texto_parcial):
        """Muestra texto en tiempo real conforme el usuario va hablando."""
        if texto_parcial:
            self.lbl_estado.text = f"Oyendo: {texto_parcial}..."

    def procesar_comando_texto(self, texto_comando):
        """Procesa y responde buscando coincidencias flexibles de palabras clave."""
        if not texto_comando:
            return

        texto = normalizar_texto(texto_comando)
        if not texto:
            return

        print(f"[BastonApp - Procesando comando]: '{texto_comando}' (norm: '{texto}')")
        self.lbl_estado.text = f"Comando: {texto_comando}"
        self.img_qr.opacity = 0

        # NODO 0: Saludo y Activación por voz
        if any(w in texto for w in ["hola", "saludo", "buenas", "activado", "estas ahi", "ayuda", "quien eres"]):
            nombre_act = self.voz.nombre_asistente.capitalize()
            self.voz.hablar(f"Hola, soy tu asistente {nombre_act}. Te escucho. Puedo ayudarte con la cámara, agenda, ubicación, documentos o guiado.")
            self.lbl_estado.text = "Asistente activo. Te escucho."
            return

        # NODO 1: Cambiar Nombre de Activación
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

        # NODO 2: Cancelar Navegación Activa
        if any(w in texto for w in ["cancelar ruta", "detener guia", "parar ruta", "cancelar navegacion", "detener navegacion", "cancelar guia"]):
            self.gps.cancelar_navegacion()
            if self.evento_navegacion:
                self.evento_navegacion.cancel()
                self.evento_navegacion = None
            self.lbl_estado.text = "Ruta cancelada."
            self.voz.hablar("Ruta de navegación cancelada.")
            return

        # NODO 3: Agenda Personal (Evaluado antes de Visión para que 'ver agenda' no active la cámara)
        if any(w in texto for w in ["borrar agenda", "limpiar agenda", "borrar recordatorios", "vaciar agenda"]):
            resumen = self.agenda.borrar_agenda()
            self.lbl_estado.text = f"Agenda: Limpiada"
            self.voz.hablar(resumen)
            return

        if any(w in texto for w in ["agenda", "mi agenda", "ver agenda", "consultar agenda", "mis recordatorios", "que tengo agendado", "mis tareas", "tareas", "recordatorios"]):
            resumen = self.agenda.consultar_agenda()
            self.lbl_estado.text = f"Agenda:\n{resumen}"
            self.voz.hablar(resumen)
            return

        if any(w in texto for w in ["anotar", "agendar", "recordar", "guardar nota", "agregar recordatorio", "nota"]):
            nota = texto_comando
            for prefijo in ["anotar", "agendar", "recordar que", "recordar", "guardar nota", "agregar recordatorio", "nota"]:
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

        # NODO 4: Lectura de Documentos, Hojas y Etiquetas
        if any(w in texto for w in ["leer", "lee", "lectura", "documento", "hoja", "etiqueta", "texto", "papel", "carta", "pagina"]):
            self.voz.hablar("Capturando documento para lectura por voz.")
            self.lector.capturar_y_leer(self.al_completar_lectura_documento)
            return

        # NODO 5: Ubicación GPS actual
        if any(w in texto for w in ["ubicacion", "donde estoy", "donde me encuentro", "donde ando", "donde me ubico", "lugar", "donde", "direccion", "posicion"]) and not any(w in texto for w in ["guia", "llevame", "ir"]):
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

        # NODO 6: Navegación y Guiado
        if any(w in texto for w in ["guiame", "guia", "llevame", "lleva", "ir a", "ir al", "ir a la", "como llego", "navegar"]):
            lugar = texto_comando
            for prefijo in ["guiame a", "guia a", "llevame a", "lleva a", "ir a", "como llego a", "navegar a", "ir al", "ir a la", "guiame", "llevame"]:
                pref_norm = normalizar_texto(prefijo)
                if pref_norm in texto:
                    idx = texto.find(pref_norm)
                    if idx != -1:
                        lugar = texto_comando[idx + len(pref_norm):].strip()
                    break
            
            if not lugar:
                lugar = "Farmacia Central"

            self.voz.hablar(f"Calculando ruta hacia {lugar}...")
            lat, lon = self.gps.obtener_coordenadas()
            mensaje_guia = self.gps.buscar_y_establecer_destino(lugar, lat, lon)
            self.lbl_estado.text = mensaje_guia
            self.voz.hablar(mensaje_guia)

            if not self.evento_navegacion:
                self.evento_navegacion = Clock.schedule_interval(self._monitorear_navegacion, 12)
            return

        # NODO 7: Conexión Bastón ESP32 / Bluetooth (Dirección MAC: 30:C9:22:32:F5:D6)
        if any(w in texto for w in ["conectar baston", "conectar", "conectate", "desconectar", "enlazar baston", "vincular baston", "bluetooth", "baston"]) and not any(w in texto for w in ["guia", "llevame", "ir", "hola", "agenda", "dime", "donde"]):
            if "desconectar" in texto:
                self.bt.desconectar()
                self.lbl_estado.text = "Bastón desconectado."
                self.voz.hablar("Bastón desconectado.")
            else:
                self.lbl_estado.text = "Estado: Conectando al Bastón ESP32 (30:C9:22:32:F5:D6)..."
                self.voz.hablar("Buscando señal del bastón. Conectando...")
                self.bt.conectar_async(self.al_completar_conexion_baston)
            return


        # NODO 8: Código QR
        if any(w in texto for w in ["qr", "comparte", "compartir", "codigo"]):
            ruta_qr = self.generar_qr_compartir()
            self.lbl_estado.text = "Código QR generado"
            if os.path.exists(ruta_qr):
                self.img_qr.source = ruta_qr
                self.img_qr.reload()
                self.img_qr.opacity = 1
            self.voz.hablar("Código QR generado en la pantalla para compartir la aplicación.")
            return

        # NODO 9: Análisis Visual Puntual (Cámara / YOLO / Obstáculos / Frente)
        if any(w in texto for w in [
            "frente", "delante", "adelante", "enfrente", "que hay", "que veo", "que ves", "que miras",
            "mira", "mirar", "ver entorno", "ver camara", "ver foto", "camara", "foto", "fotografia",
            "obstaculo", "obstaculos", "objeto", "objetos", "analizar", "escaneo", "escanea", "que tenemos"
        ]):
            self.voz.hablar("Analizando el entorno con la cámara.")
            self.vision.capturar_y_analizar(self.al_completar_analisis_vision)
            return

        # NODO 10: Guardar Clave API de Gemini por Voz o Teclado
        if any(w in texto for w in ["guardar clave", "guardar api key", "guardar clave api"]):
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
                    self.lbl_estado.text = "Clave API de Gemini guardada."
                    self.voz.hablar("Clave API de Gemini guardada correctamente.")
                else:
                    self.lbl_estado.text = "Error al guardar API Key."
                    self.voz.hablar("Ocurrió un error al guardar la clave.")
            else:
                self.voz.hablar("No detecté la clave API. Repite guardar clave seguido de tu clave.")
            return

        # NODO 11: Consultas Locales Offline (Hora, Fecha, Identidad, Estado)
        res_local = self.ai.responder_consulta_local(texto, texto_comando)
        if res_local:
            self.lbl_estado.text = res_local
            self.voz.hablar(res_local)
            return

        # NODO 12: IA Conversacional Gemini (Preguntas Libres del Usuario)
        self.lbl_estado.text = f"Consultando IA: {texto_comando}"
        self.voz.hablar("Pensando...")
        self.ai.consultar_gemini_async(texto_comando, self.al_recibir_respuesta_gemini)

    def al_recibir_respuesta_gemini(self, respuesta):
        """Recibe la respuesta generada por Gemini y la reproduce por voz."""
        self.lbl_estado.text = f"IA: {respuesta}"
        self.voz.hablar(respuesta)




    def _monitorear_navegacion(self, dt):
        """Monitorea el avance del usuario hacia el destino y emite avisos por voz."""
        if not self.gps.navegacion_activa:
            if self.evento_navegacion:
                self.evento_navegacion.cancel()
                self.evento_navegacion = None
            return

        lat, lon = self.gps.obtener_coordenadas()
        instruccion = self.gps.obtener_instruccion_guia(lat, lon)
        if instruccion:
            self.lbl_estado.text = f"Navegación:\n{instruccion}"
            self.voz.hablar(instruccion)

    def al_recibir_alerta_baston(self, mensaje_alerta):
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
                self.lbl_estado.text = "Estado: Conectado al Bastón ESP32 (30:C9:22:32:F5:D6)"
                self.voz.hablar("Conectado.")
                self.bt.escuchar_alertas_baston(self.al_recibir_alerta_baston, self.al_cambio_estado_baston)
            else:
                self.lbl_estado.text = "Bastón no detectado. Modo autónomo."
                self.voz.hablar("No se detectó el bastón. La aplicación sigue completamente activa.")
        Clock.schedule_once(actualizar_ui, 0)


    def _actualizar_ui_alerta(self, mensaje_alerta):
        self.lbl_estado.text = f"¡ALERTA!: {mensaje_alerta}"
        self.voz.hablar(mensaje_alerta)

    def al_completar_analisis_vision(self, resultado_texto):
        self.lbl_estado.text = f"Visión: {resultado_texto}"
        self.voz.hablar(resultado_texto)

    def al_completar_lectura_documento(self, texto_leido):
        self.lbl_estado.text = f"Lectura: {texto_leido}"
        self.voz.hablar(texto_leido)

    def generar_qr_compartir(self):
        if not qrcode:
            return ""
        url_repo = "https://github.com/Miguel-Quispe/bastonDesgraciado"
        img = qrcode.make(url_repo)
        ruta_salida = "qr_app.png"
        img.save(ruta_salida)
        return ruta_salida

    def on_stop(self):
        """Cierre limpio de conexiones y servicios."""
        if self.evento_navegacion:
            self.evento_navegacion.cancel()
        if hasattr(self, 'voz'):
            self.voz.detener_escucha()
        if hasattr(self, 'bt'):
            self.bt.desconectar()

if __name__ == '__main__':
    BastonApp().run()
