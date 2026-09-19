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
        
        # Palabras de activación configurables (por defecto: bastón / oye bastón)
        self.palabras_activacion = palabras_activacion if palabras_activacion is not None else ["bastón", "baston", "oye baston", "oye bastón", "hola baston", "hola bastón"]
        self.requiere_palabra_activacion = True
        
        # Ruta del modelo Vosk
        self.ruta_modelo = ruta_modelo if os.path.isabs(ruta_modelo) else os.path.join(os.getcwd(), ruta_modelo)
        
        self._inicializar_android()
        self._inicializar_vosk()

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
        """Inicializa el modelo de Vosk si la carpeta existe."""
        try:
            from vosk import Model, KaldiRecognizer
            if os.path.exists(self.ruta_modelo):
                print(f"[SpeechEngine] Cargando modelo Vosk desde: {self.ruta_modelo} ...")
                self.modelo_vosk = Model(self.ruta_modelo)
                self.reconocedor_vosk = KaldiRecognizer(self.modelo_vosk, 16000)
                print("[SpeechEngine] Modelo Vosk cargado exitosamente. Reconocimiento offline listo.")
            else:
                print(f"[SpeechEngine] Aviso: Carpeta de modelo Vosk '{self.ruta_modelo}' no encontrada. Se usará modo simulación.")
        except Exception as e:
            print(f"[SpeechEngine] Error al cargar Vosk ({e}). Modo simulación.")

    def hablar(self, texto):
        """Convierte texto a voz mediante el motor nativo de Android o consola en desarrollo."""
        print(f"[TTS Audio Output]: {texto}")
        if self.tts:
            try:
                from jnius import autoclass
                Locale = autoclass('java.util.Locale')
                self.tts.setLanguage(Locale("es", "ES"))
                # QUEUE_FLUSH = 0 para interrumpir y hablar de inmediato
                self.tts.speak(texto, 0, None, None)
            except Exception as e:
                print(f"[SpeechEngine] Error al reproducir TTS: {e}")

    def estan_auriculares_conectados(self):
        """Verifica si hay auriculares conectados por cable o Bluetooth."""
        if self.activity:
            try:
                from jnius import autoclass
                Context = autoclass('android.content.Context')
                audio_manager = self.activity.getSystemService(Context.AUDIO_SERVICE)
                
                if audio_manager:
                    wired = audio_manager.isWiredHeadsetOn()
                    bluetooth = audio_manager.isBluetoothA2dpOn()
                    return wired or bluetooth
            except Exception as e:
                print(f"[SpeechEngine] Error al comprobar auriculares: {e}")
        return False

    def iniciar_escucha_continua(self, callback_comando, callback_parcial=None):
        """Inicia el hilo de escucha continua en segundo plano."""
        if self.escuchando:
            return

        self.escuchando = True
        self.hilo_escucha = threading.Thread(
            target=self._loop_escucha_continua, 
            args=(callback_comando, callback_parcial),
            daemon=True
        )
        self.hilo_escucha.start()
        print("[SpeechEngine] Escucha continua offline iniciada.")

    def detener_escucha(self):
        """Detiene el hilo de escucha continua."""
        self.escuchando = False
        print("[SpeechEngine] Escucha continua detenida.")

    def _loop_escucha_continua(self, callback_comando, callback_parcial):
        """Bucle en segundo plano que graba audio y lo procesa con Vosk."""
        # 1. Modo Android nativo con AudioRecord
        if self.activity and self.reconocedor_vosk:
            self._grabar_audio_android(callback_comando, callback_parcial)
        # 2. Modo PC con PyAudio si está instalado y el modelo existe
        elif self.reconocedor_vosk:
            self._grabar_audio_desktop(callback_comando, callback_parcial)
        # 3. Fallback de simulación
        else:
            self._simular_escucha_continua(callback_comando)

    def _grabar_audio_android(self, callback_comando, callback_parcial):
        try:
            from jnius import autoclass
            AudioRecord = autoclass('android.media.AudioRecord')
            AudioFormat = autoclass('android.media.AudioFormat')
            MediaRecorder = autoclass('android.media.MediaRecorder')
            
            sample_rate = 16000
            channel_config = AudioFormat.CHANNEL_IN_MONO
            audio_format = AudioFormat.ENCODING_PCM_16BIT
            
            min_buf_size = AudioRecord.getMinBufferSize(sample_rate, channel_config, audio_format)
            buffer_size = max(min_buf_size, 4096)
            
            recorder = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sample_rate,
                channel_config,
                audio_format,
                buffer_size
            )
            
            recorder.startRecording()
            byte_array = bytearray(buffer_size)
            
            while self.escuchando:
                num_read = recorder.read(byte_array, 0, len(byte_array))
                if num_read > 0:
                    data = bytes(byte_array[:num_read])
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
                            
            recorder.stop()
            recorder.release()
        except Exception as e:
            print(f"[SpeechEngine] Error en captura AudioRecord Android: {e}")

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
        except ImportError:
            print("[SpeechEngine] PyAudio no está instalado en PC. Usando simulación.")
            self._simular_escucha_continua(callback_comando)
        except Exception as e:
            print(f"[SpeechEngine] Error en captura Desktop: {e}")

    def _simular_escucha_continua(self, callback_comando):
        """Simula comandos periódicos en modo de desarrollo sin hardware."""
        while self.escuchando:
            time.sleep(15)
            if self.escuchando:
                print("[SpeechEngine - Simulación]: Comando recibido offline")
                Clock.schedule_once(lambda dt: callback_comando("bastón dónde estoy"), 0)

    def _procesar_texto_reconocido(self, texto_completo, callback_comando):
        """Filtra y limpia el texto reconociendo si incluye o no la palabra de activación."""
        texto_lower = texto_completo.lower().strip()
        print(f"[SpeechEngine - Reconocido]: '{texto_lower}'")
        
        if not self.requiere_palabra_activacion:
            Clock.schedule_once(lambda dt: callback_comando(texto_lower), 0)
            return

        # Verificar si contiene alguna de las palabras de activación
        activado = False
        comando_limpio = texto_lower
        
        for palabra in self.palabras_activacion:
            if palabra in texto_lower:
                activado = True
                # Remover la palabra clave para dejar solo la instrucción
                comando_limpio = texto_lower.replace(palabra, "").strip()
                break

        if activado:
            Clock.schedule_once(lambda dt: callback_comando(comando_limpio if comando_limpio else "activado"), 0)
