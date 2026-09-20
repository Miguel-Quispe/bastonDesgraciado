import os
import json
import threading
import time
from kivy.clock import Clock

class SpeechEngine:
    def __init__(self, ruta_modelo="model", palabras_activacion=None):
        self.tts = None
        self.activity = None
        self.escuchando = False
        self.hilo_escucha = None
        self.reconocedor_vosk = None
        self.modelo_vosk = None
        
        # Archivo de configuración persistente
        self.archivo_config = os.path.join(os.getcwd(), "config_asistente.json")
        self.nombre_asistente = self._cargar_config_nombre()

        # Palabras de activación configurables (dinámicas según el nombre guardado)
        if palabras_activacion is not None:
            self.palabras_activacion = palabras_activacion
        else:
            self._reconstruir_palabras_activacion()

        self.requiere_palabra_activacion = True
        self.ruta_modelo = ruta_modelo if os.path.isabs(ruta_modelo) else os.path.join(os.getcwd(), ruta_modelo)
        
        self._inicializar_android()
        self._inicializar_vosk()

    def _cargar_config_nombre(self):
        """Carga el nombre personalizado del asistente guardado en disco."""
        try:
            if os.path.exists(self.archivo_config):
                with open(self.archivo_config, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("nombre", "bastón").lower().strip()
        except Exception as e:
            print(f"[SpeechEngine] Error al cargar config nombre: {e}")
        return "bastón"

    def _reconstruir_palabras_activacion(self):
        """Genera el listado de frases de activación con el nombre activo."""
        nombre = self.nombre_asistente
        self.palabras_activacion = [
            nombre,
            f"oye {nombre}",
            f"hola {nombre}",
            f"ok {nombre}",
            "bastón", "baston" # Respaldo secundario siempre disponible
        ]

    def actualizar_nombre_asistente(self, nuevo_nombre):
        """Cambia el nombre de activación del asistente y lo guarda de forma persistente."""
        nombre_limpio = nuevo_nombre.lower().strip()
        if not nombre_limpio:
            return

        self.nombre_asistente = nombre_limpio
        self._reconstruir_palabras_activacion()

        try:
            with open(self.archivo_config, "w", encoding="utf-8") as f:
                json.dump({"nombre": self.nombre_asistente}, f, ensure_ascii=False)
        except Exception as e:
            print(f"[SpeechEngine] Error al guardar config de nombre: {e}")

        self.hablar(f"Entendido. A partir de ahora responderé al nombre de {self.nombre_asistente.capitalize()}.")

    def _inicializar_android(self):
        try:
            from jnius import autoclass
            self.TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.activity = self.PythonActivity.mActivity
            self.tts = self.TextToSpeech(self.activity, None)
            print("[SpeechEngine] Motor TTS de Android inicializado correctamente.")
        except Exception as e:
            print(f"[SpeechEngine] No se pudo inicializar TTS nativo de Android ({e}). Modo consola activado.")
            self.tts = None

    def _inicializar_vosk(self):
        """Inicializa el modelo de Vosk si la carpeta existe en PC/desarrollo."""
        try:
            from vosk import Model, KaldiRecognizer
            if os.path.exists(self.ruta_modelo):
                print(f"[SpeechEngine] Cargando modelo Vosk desde: {self.ruta_modelo} ...")
                self.modelo_vosk = Model(self.ruta_modelo)
                self.reconocedor_vosk = KaldiRecognizer(self.modelo_vosk, 16000)
                print("[SpeechEngine] Modelo Vosk cargado exitosamente.")
            else:
                print(f"[SpeechEngine] Aviso: Modelo Vosk no presente.")
        except Exception as e:
            print(f"[SpeechEngine] Vosk no disponible: {e}")

    def hablar(self, texto, reintentos=2):
        """Convierte texto a voz mediante el motor nativo de Android o consola en desarrollo."""
        print(f"[TTS Audio Output]: {texto}")
        if self.tts:
            try:
                from jnius import autoclass
                Locale = autoclass('java.util.Locale')
                self.tts.setLanguage(Locale("es", "ES"))
                res = self.tts.speak(texto, 0, None, None)
                if res != 0 and reintentos > 0:
                    Clock.schedule_once(lambda dt: self.hablar(texto, reintentos - 1), 0.8)
            except Exception as e:
                print(f"[SpeechEngine] Error al reproducir TTS: {e}")

    def estan_auriculares_conectados(self):
        """Verifica si hay auriculares conectados por cable de forma segura."""
        if self.activity:
            try:
                from jnius import autoclass
                Context = autoclass('android.content.Context')
                audio_manager = self.activity.getSystemService(Context.AUDIO_SERVICE)
                if audio_manager:
                    try:
                        return bool(audio_manager.isWiredHeadsetOn())
                    except Exception:
                        pass
            except Exception as e:
                print(f"[SpeechEngine] Aviso al comprobar auriculares: {e}")
        return False

    def iniciar_escucha_continua(self, callback_comando, callback_parcial=None):
        """Inicia el reconocimiento de voz continuo en Android o escritorio."""
        if self.escuchando:
            return

        self.escuchando = True
        self.hilo_escucha = threading.Thread(
            target=self._loop_escucha_continua, 
            args=(callback_comando, callback_parcial),
            daemon=True
        )
        self.hilo_escucha.start()
        print("[SpeechEngine] Escucha continua iniciada.")

    def detener_escucha(self):
        """Detiene el hilo de escucha continua."""
        self.escuchando = False
        print("[SpeechEngine] Escucha continua detenida.")

    def _loop_escucha_continua(self, callback_comando, callback_parcial):
        """Usa SpeechRecognizer nativo en Android o PyAudio/Vosk en PC."""
        if self.activity:
            self._iniciar_reconocimiento_nativo_android(callback_comando, callback_parcial)
        elif self.reconocedor_vosk:
            self._grabar_audio_desktop(callback_comando, callback_parcial)
        else:
            self._simular_escucha_continua(callback_comando)

    def _iniciar_reconocimiento_nativo_android(self, callback_comando, callback_parcial=None):
        """Inicia el reconocedor de voz nativo de Android (android.speech.SpeechRecognizer)."""
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            
            SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
            Intent = autoclass('android.content.Intent')
            RecognizerIntent = autoclass('android.speech.RecognizerIntent')

            class EscuchadorAndroid(PythonJavaClass):
                __javainterfaces__ = ['android/speech/RecognitionListener']

                def __init__(self, engine, callback_cmd, callback_prc):
                    super().__init__()
                    self.engine = engine
                    self.callback_cmd = callback_cmd
                    self.callback_prc = callback_prc

                @java_method('(Landroid/os/Bundle;)V')
                def onReadyForSpeech(self, params):
                    print("[SpeechRecognizer Android] Micrófono listo para escuchar.")

                @java_method('()V')
                def onBeginningOfSpeech(self):
                    pass

                @java_method('(F)V')
                def onRmsChanged(self, rmsdB):
                    pass

                @java_method('([B)V')
                def onBufferReceived(self, buffer):
                    pass

                @java_method('()V')
                def onEndOfSpeech(self):
                    pass

                @java_method('(I)V')
                def onError(self, error):
                    print(f"[SpeechRecognizer Android] Aviso reconocimiento ({error}). Reanudando...")
                    if self.engine.escuchando:
                        Clock.schedule_once(lambda dt: self.engine._reiniciar_escucha_android(), 1.0)

                @java_method('(Landroid/os/Bundle;)V')
                def onResults(self, results):
                    try:
                        matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        if matches and matches.size() > 0:
                            texto = str(matches.get(0)).strip()
                            print(f"[SpeechRecognizer Texto Reconocido]: '{texto}'")
                            self.engine._procesar_texto_reconocido(texto, self.callback_cmd)
                    except Exception as e:
                        print(f"[SpeechRecognizer Error Resultados]: {e}")
                    
                    if self.engine.escuchando:
                        Clock.schedule_once(lambda dt: self.engine._reiniciar_escucha_android(), 0.4)

                @java_method('(Landroid/os/Bundle;)V')
                def onPartialResults(self, partialResults):
                    try:
                        matches = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        if matches and matches.size() > 0 and self.callback_prc:
                            parcial = str(matches.get(0)).strip()
                            Clock.schedule_once(lambda dt, p=parcial: self.callback_prc(p), 0)
                    except Exception:
                        pass

                @java_method('(ILandroid/os/Bundle;)V')
                def onEvent(self, eventType, params):
                    pass

            self.escuchador_listener = EscuchadorAndroid(self, callback_comando, callback_parcial)
            
            def iniciar_en_main_thread(dt):
                try:
                    self.speech_rec = SpeechRecognizer.createSpeechRecognizer(self.activity)
                    self.speech_rec.setRecognitionListener(self.escuchador_listener)
                    
                    self.intent_escucha = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-ES")
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
                    
                    self.speech_rec.startListening(self.intent_escucha)
                    print("[SpeechEngine Android] Recognizer nativo iniciado exitosamente.")
                except Exception as e:
                    print(f"[SpeechEngine Android Error Iniciar]: {e}")

            Clock.schedule_once(iniciar_en_main_thread, 0.5)
        except Exception as e:
            print(f"[SpeechEngine Android Error Listener]: {e}")

    def _reiniciar_escucha_android(self):
        if self.escuchando and hasattr(self, 'speech_rec') and self.speech_rec and hasattr(self, 'intent_escucha'):
            try:
                self.speech_rec.startListening(self.intent_escucha)
            except Exception as e:
                print(f"[SpeechEngine Android Error Reanudar]: {e}")

    def _grabar_audio_desktop(self, callback_comando, callback_parcial):
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)
            stream.start_stream()
            
            while self.escuchando:
                data = stream.read(4000, exception_on_overflow=False)
                if self.reconocedor_vosk.AcceptWaveform(data):
                    res = json.loads(self.reconocedor_vosk.Result())
                    texto = res.get("text", "").strip()
                    if texto:
                        self._procesar_texto_reconocido(texto, callback_comando)
                elif callback_parcial:
                    partial_res = json.loads(self.reconocedor_vosk.PartialResult())
                    parcial = partial_res.get("partial", "").strip()
                    if parcial:
                        Clock.schedule_once(lambda dt, p=parcial: callback_parcial(p), 0)
                        
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            print(f"[SpeechEngine] Error en captura Desktop: {e}")
            self._simular_escucha_continua(callback_comando)

    def _simular_escucha_continua(self, callback_comando):
        """Simula comandos periódicos en modo de desarrollo sin hardware."""
        while self.escuchando:
            time.sleep(15)
            if self.escuchando:
                print("[SpeechEngine - Simulación]: Comando recibido")
                Clock.schedule_once(lambda dt: callback_comando("bastón dónde estoy"), 0)

    def _procesar_texto_reconocido(self, texto_completo, callback_comando):
        """Filtra y limpia el texto reconociendo si incluye o no la palabra de activación."""
        texto_lower = texto_completo.lower().strip()
        print(f"[SpeechEngine - Reconocido]: '{texto_lower}'")
        if not texto_lower:
            return

        activado = False
        comando_limpio = texto_lower
        
        # 1. Comprobar palabras de activación (ej. bastón, rayo, oye rayo, hola rayo)
        for palabra in self.palabras_activacion:
            if palabra in texto_lower:
                activado = True
                comando_limpio = texto_lower.replace(palabra, "").strip()
                break

        # 2. Si no incluía la palabra clave exacta pero contiene una intención directa (ej. "hola", "dónde estoy")
        if not activado:
            comandos_directos = ["hola", "saludo", "ayuda", "dónde estoy", "donde estoy", "ubicación", "guíame", "guiame", "llévame", "llevame", "foto", "mira", "leer", "agenda", "anotar", "conectar", "desconectar"]
            if any(cmd in texto_lower for cmd in comandos_directos):
                activado = True

        if activado:
            instruccion = comando_limpio if comando_limpio else "hola"
            Clock.schedule_once(lambda dt: callback_comando(instruccion), 0)
