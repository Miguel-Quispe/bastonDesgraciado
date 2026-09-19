import os
import qrcode
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

class BastonApp(App):
    def build(self):
        self.title = "Bastón Inteligente - Asistente Autónomo"
        # Ajuste visual para accesibilidad de alto contraste
        Window.clearcolor = (0.05, 0.08, 0.12, 1)

        self.bt = BluetoothManager()
        self.voz = SpeechEngine()
        self.gps = LocationService()
        self.vision = VisionAnalyzer()

        self.layout = BoxLayout(orientation='vertical', padding=25, spacing=20)
        
        self.lbl_estado = Label(
            text="Asistente de Autonomía\nEscucha continua activa. Di 'Bastón' seguido de tu comando.",
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

    def on_start(self):
        """Inicia los servicios automáticos al abrir la aplicación."""
        # 1. Sugerencia de auriculares si no están conectados
        if not self.voz.estan_auriculares_conectados():
            self.voz.hablar("Bienvenido. ¿Deseas conectar auriculares para mayor privacidad? La escucha continua está activa.")
        else:
            self.voz.hablar("Asistente listo. Te escucho.")

        # 2. Iniciar escucha continua offline con Vosk
        self.voz.iniciar_escucha_continua(
            callback_comando=self.procesar_comando_texto,
            callback_parcial=self.al_recibir_parcial
        )

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

        # NODO 1: Conexión con el Bastón ESP32
        if any(w in texto for w in ["conectar", "conéctate", "conectate", "baston", "bastón", "enlazar"]):
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

        # NODO 2: Petición de Ubicación GPS y Geocodificación
        elif any(w in texto for w in ["ubicación", "ubicacion", "dónde estoy", "donde estoy", "lugar"]):
            self.voz.hablar("Obteniendo tu ubicación actual.")
            lat, lon = self.gps.obtener_coordenadas()
            if lat is not None:
                direccion = self.gps.consultar_direccion_mapbox(lat, lon)
                self.lbl_estado.text = f"Ubicación:\n{direccion}"
                self.voz.hablar(f"Te encuentras en: {direccion}")
            else:
                self.voz.hablar("No se pudo obtener la señal GPS.")
                self.lbl_estado.text = "Error: GPS no disponible"

        # NODO 3: Generación de QR de la App
        elif any(w in texto for w in ["qr", "comparte", "compartir", "código", "codigo"]):
            ruta_qr = self.generar_qr_compartir()
            self.lbl_estado.text = "Código QR generado"
            if os.path.exists(ruta_qr):
                self.img_qr.source = ruta_qr
                self.img_qr.reload()
                self.img_qr.opacity = 1
            self.voz.hablar("Código QR generado en la pantalla para compartir la aplicación.")

        # NODO 4: Análisis Visual Puntual con Cámara e IA MiniCPM-5
        elif any(w in texto for w in ["foto", "ver", "cámara", "camara", "entorno", "obstáculo", "obstaculo", "mira", "que hay", "qué hay"]):
            self.voz.hablar("Analizando el entorno con la cámara.")
            self.vision.capturar_y_analizar(self.al_completar_analisis_vision)

        # NODO 5: Saludo o activación simple
        elif texto in ["activado", "hola", "estás ahí", "estas ahi", "ayuda"]:
            self.voz.hablar("Sí, aquí estoy. Puedes pedirme tu ubicación, conectar el bastón o analizar el entorno.")
            self.lbl_estado.text = "Listo para tus comandos."

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

    def generar_qr_compartir(self):
        url_repo = "https://github.com/adidas2019x"
        img = qrcode.make(url_repo)
        ruta_salida = "qr_app.png"
        img.save(ruta_salida)
        return ruta_salida

    def on_stop(self):
        """Cierre limpio de conexiones y servicios."""
        if hasattr(self, 'voz'):
            self.voz.detener_escucha()
        if hasattr(self, 'bt'):
            self.bt.desconectar()

if __name__ == '__main__':
    BastonApp().run()
