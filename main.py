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
from kivy.core.window import Window
from kivy.clock import Clock

from modules.bluetooth_manager import BluetoothManager
from modules.speech_engine import SpeechEngine
from modules.location_service import LocationService
from modules.vision_analyzer import VisionAnalyzer
from modules.agenda_manager import AgendaManager
from modules.document_reader import DocumentReader

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
        self.evento_navegacion = None

        self.layout = BoxLayout(orientation='vertical', padding=25, spacing=20)
        
        self.lbl_estado = Label(
            text="Asistente de Autonomía\nEscucha activa. Di 'Bastón' seguido de tu comando.",
            font_size='22sp',
            bold=True,
            color=(1, 1, 1, 1),
            halign='center',
            valign='middle'
        )
        self.lbl_estado.bind(size=self.lbl_estado.setter('text_size'))
        self.layout.add_widget(self.lbl_estado)

        self.img_qr = Image(
            size_hint=(1, 0.3),
            opacity=0
        )
        self.layout.add_widget(self.img_qr)

        self.btn_accion = Button(
            text="🎤 ESCUCHA ACTIVA\n(Toca para pausar/reanudar)",
            font_size='22sp',
            bold=True,
            size_hint=(1, 0.35),
            background_normal='',
            background_color=(0.1, 0.65, 0.45, 1),
            color=(1, 1, 1, 1),
            halign='center'
        )
        self.btn_accion.bind(on_press=self.al_presionar_boton_escucha)
        self.layout.add_widget(self.btn_accion)

        return self.layout

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

        nombre_actual = self.voz.nombre_asistente.capitalize()
        mensaje_bienvenida = f"Aplicación iniciada. Asistente activo con el nombre {nombre_actual}. Te escucho. Di {nombre_actual} seguido de tu comando."
        
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

    def al_presionar_boton_escucha(self, instance):
        """Alterna entre pausar y reactivar la escucha continua."""
        if self.voz.escuchando:
            self.voz.detener_escucha()
            self.btn_accion.text = "🔇 ESCUCHA PAUSADA\n(Toca para reactivar)"
            self.btn_accion.background_color = (0.8, 0.2, 0.2, 1)
            self.lbl_estado.text = "Micrófono pausado."
            self.voz.hablar("Micrófono pausado.")
        else:
            self.voz.iniciar_escucha_continua(
                callback_comando=self.procesar_comando_texto,
                callback_parcial=self.al_recibir_parcial
            )
            self.btn_accion.text = "🎤 ESCUCHA ACTIVA\n(Toca para pausar)"
            self.btn_accion.background_color = (0.1, 0.65, 0.45, 1)
            self.lbl_estado.text = "Escucha reactivada. Te escucho."
            self.voz.hablar("Escucha reactivada.")

    def al_recibir_parcial(self, texto_parcial):
        """Muestra texto en tiempo real conforme el usuario va hablando."""
        if texto_parcial:
            self.lbl_estado.text = f"Oyendo: {texto_parcial}..."

    def procesar_comando_texto(self, texto_comando):
        """Procesa y responde únicamente cuando se detecta un comando o consulta."""
        texto = texto_comando.lower().strip()
        if not texto:
            return

        self.lbl_estado.text = f"Comando: {texto}"
        self.img_qr.opacity = 0

        # NODO 0: Personalizar Nombre de Activación del Asistente (ej. "cambiar nombre a Rayo", "llámate Rayo", "tu nuevo nombre es Rayo")
        if any(w in texto for w in ["cambiar nombre a", "cambiar palabra a", "llámate", "llamate", "tu nombre es", "nuevo nombre", "llamarte"]):
            nuevo_nombre = texto
            for prefijo in ["cambiar nombre a", "cambiar palabra a", "llámate a", "llamate a", "llámate", "llamate", "tu nombre es", "nuevo nombre", "llamarte"]:
                if prefijo in nuevo_nombre:
                    nuevo_nombre = nuevo_nombre.split(prefijo)[-1].strip()
                    break
            
            if nuevo_nombre:
                self.voz.actualizar_nombre_asistente(nuevo_nombre)
                self.lbl_estado.text = f"Nombre del asistente: {nuevo_nombre.capitalize()}"
            else:
                self.voz.hablar(f"No entendí el nuevo nombre. Mi nombre actual es {self.voz.nombre_asistente.capitalize()}.")
            return

        # NODO 1: Conexión con el Bastón ESP32
        if any(w in texto for w in ["conectar", "conéctate", "conectate", "baston", "bastón", "enlazar"]) and not any(w in texto for w in ["guía", "guia", "llévame", "llevame", "ir"]):
            if "desconectar" in texto:
                self.bt.desconectar()
                self.lbl_estado.text = "Bastón desconectado."
                self.voz.hablar("Bastón desconectado.")
            else:
                self.voz.hablar("Conectando con el bastón.")
                exito = self.bt.conectar()
                if exito:
                    self.voz.hablar("Conectado con éxito al bastón.")
                    self.lbl_estado.text = "Estado: Conectado al Bastón ESP32"
                    self.bt.escuchar_alertas_baston(self.al_recibir_alerta_baston, self.al_cambio_estado_baston)
                else:
                    self.voz.hablar("No se pudo establecer la conexión Bluetooth con el bastón.")
                    self.lbl_estado.text = "Error: Sin conexión Bluetooth"

        # NODO 2: Navegación y Guiado a un Destino (Voz o Coordenadas)
        elif any(w in texto for w in ["guíame", "guiame", "llévame", "llevame", "ir a", "cómo llego", "como llego", "navegar a"]):
            lugar = texto
            for prefijo in ["guíame a", "guiame a", "llévame a", "llevame a", "ir a", "cómo llego a", "como llego a", "navegar a"]:
                if prefijo in lugar:
                    lugar = lugar.split(prefijo)[-1].strip()
                    break
            
            if not lugar:
                lugar = "Farmacia Central"

            self.voz.hablar(f"Calculando ruta hacia {lugar}...")
            lat, lon = self.gps.obtener_coordenadas()
            mensaje_guia = self.gps.buscar_y_establecer_destino(lugar, lat, lon)
            self.lbl_estado.text = mensaje_guia
            self.voz.hablar(mensaje_guia)

            # Iniciar monitoreo periódico de guiado
            if not self.evento_navegacion:
                self.evento_navegacion = Clock.schedule_interval(self._monitorear_navegacion, 12)

        # NODO 3: Cancelar Navegación Activa
        elif any(w in texto for w in ["cancelar ruta", "detener guía", "detener guia", "parar ruta", "cancelar navegación"]):
            self.gps.cancelar_navegacion()
            if self.evento_navegacion:
                self.evento_navegacion.cancel()
                self.evento_navegacion = None
            self.lbl_estado.text = "Ruta cancelada."
            self.voz.hablar("Ruta de navegación cancelada.")

        # NODO 4: Petición de Ubicación GPS actual
        elif any(w in texto for w in ["ubicación", "ubicacion", "dónde estoy", "donde estoy", "lugar"]) and not any(w in texto for w in ["guía", "guia", "llévame"]):
            self.voz.hablar("Obteniendo tu ubicación actual.")
            lat, lon = self.gps.obtener_coordenadas()
            if lat is not None:
                direccion = self.gps.consultar_direccion_mapbox(lat, lon)
                self.lbl_estado.text = f"Ubicación:\n{direccion}"
                self.voz.hablar(f"Te encuentras en: {direccion}")
            else:
                self.voz.hablar("No se pudo obtener la señal GPS.")
                self.lbl_estado.text = "Error: GPS no disponible"

        # NODO 5: Generación de QR de la App
        elif any(w in texto for w in ["qr", "comparte", "compartir", "código", "codigo"]):
            ruta_qr = self.generar_qr_compartir()
            self.lbl_estado.text = "Código QR generado"
            if os.path.exists(ruta_qr):
                self.img_qr.source = ruta_qr
                self.img_qr.reload()
                self.img_qr.opacity = 1
            self.voz.hablar("Código QR generado en la pantalla para compartir la aplicación.")

        # NODO 6: Análisis Visual Puntual con Cámara e IA YOLO
        elif any(w in texto for w in ["foto", "ver", "cámara", "camara", "entorno", "obstáculo", "obstaculo", "mira", "que hay", "qué hay"]):
            self.voz.hablar("Analizando el entorno con la cámara.")
            self.vision.capturar_y_analizar(self.al_completar_analisis_vision)

        # NODO 7: Lectura de Documentos, Hojas y Etiquetas por Voz
        elif any(w in texto for w in ["leer documento", "lee documento", "leer hoja", "lee esta hoja", "leer texto", "lee el texto", "leer etiqueta", "lee la etiqueta", "lectura"]):
            self.voz.hablar("Capturando documento para lectura por voz.")
            self.lector.capturar_y_leer(self.al_completar_lectura_documento)

        # NODO 8: Agenda Personal por Voz (Consultar, Anotar o Limpiar)
        elif any(w in texto for w in ["mi agenda", "ver agenda", "consultar agenda", "mis recordatorios", "qué tengo agendado", "que tengo agendado"]):
            resumen = self.agenda.consultar_agenda()
            self.lbl_estado.text = f"Agenda:\n{resumen}"
            self.voz.hablar(resumen)

        elif any(w in texto for w in ["borrar agenda", "limpiar agenda", "borrar recordatorios"]):
            resumen = self.agenda.borrar_agenda()
            self.lbl_estado.text = f"Agenda: Limpiada"
            self.voz.hablar(resumen)

        elif any(w in texto for w in ["anotar", "agendar", "recordar", "guardar nota", "agregar recordatorio"]):
            nota = texto
            for prefijo in ["anotar", "agendar", "recordar que", "recordar", "guardar nota", "agregar recordatorio"]:
                if prefijo in nota:
                    nota = nota.split(prefijo)[-1].strip()
                    break
            resumen = self.agenda.agregar_evento(nota if nota else texto)
            self.lbl_estado.text = f"Agenda:\n{resumen}"
            self.voz.hablar(resumen)

        # NODO 9: Saludo o activación simple
        elif texto in ["activado", "hola", "estás ahí", "estas ahi", "ayuda"]:
            self.voz.hablar("Sí, aquí estoy. Puedo ayudarte a leer documentos, gestionar tu agenda, guiarte a un lugar, conectar tu bastón o analizar el entorno.")
            self.lbl_estado.text = "Listo para tus comandos."

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
