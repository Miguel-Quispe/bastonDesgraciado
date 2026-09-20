import os
import json
import threading
import time
import queue
import unicodedata
import re
from kivy.clock import Clock

def normalizar_texto(texto):
    """Limpia el texto convirtiendo a minúsculas, quitando acentos y signos de puntuación."""
    if not texto:
        return ""
    s = str(texto).lower().strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


class SpeechEngine:
    def __init__(self, ruta_modelo="model", palabras_activacion=None):
        self.tts = None
        self.activity = None
        self.escuchando = False
        self.hilo_escucha = None
        self.reconocedor_vosk = None
        self.modelo_vosk = None
        self.reproduciendo_tts = False  # Previene que el micrófono escuche a los propios parlantes
        self._reiniciando_mic = False    # Antirrebote: evita reinicios simultáneos del mic
        self._ultimo_reinicio_mic = 0    # Timestamp del último reinicio exitoso
        self._evento_reinicio_mic = None # Referencia al Clock.schedule_once pendiente (para cancelarlo)
        self._errores_mic_consecutivos = 0
        self._ultimo_texto_parcial = ""

        # Cola y Hilo dedicado para síntesis de voz en PC (evita cierres o cuelgues SAPI5)
        self._cola_tts = queue.Queue()
        self._hilo_tts_pc = threading.Thread(target=self._loop_tts_pc, daemon=True)
        self._hilo_tts_pc.start()

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
            from jnius import autoclass, PythonJavaClass, java_method
            self.TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.activity = self.PythonActivity.mActivity
            self.tts_listo = False

            class TTSInitListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']
                def __init__(self, engine):
                    super().__init__()
                    self.engine = engine

                @java_method('(I)V')
                def onInit(self, status):
                    if status == 0:  # TextToSpeech.SUCCESS = 0
                        print("[SpeechEngine Android] TextToSpeech inicializado con ÉXITO en Android.")
                        self.engine.tts_listo = True
                        try:
                            Locale = autoclass('java.util.Locale')
                            self.engine.tts.setLanguage(Locale("es", "ES"))
                        except Exception as e:
                            print(f"[SpeechEngine Android] Error al establecer idioma es-ES: {e}")
                    else:
                        print(f"[SpeechEngine Android] TextToSpeech falló al inicializar (status={status}).")

            self.tts_listener = TTSInitListener(self)
            self.tts = self.TextToSpeech(self.activity, self.tts_listener)
            print("[SpeechEngine] Motor TTS de Android instanciado. Esperando onInit...")
        except Exception as e:
            print(f"[SpeechEngine] TTS de Android no activo ({e}). Se usará motor PC dedicado.")
            self.tts = None
            self.tts_listo = False

    def _loop_tts_pc(self):
        """Hilo único dedicado para voz en PC con SAPI.SpVoice nativo de Windows, pyttsx3 y PowerShell."""
        sp_voice = None
        try:
            import comtypes.client
            sp_voice = comtypes.client.CreateObject("SAPI.SpVoice")
            print("[SpeechEngine] Motor SAPI5 SpVoice nativo de Windows activado exitosamente.")
        except Exception as e:
            print(f"[SpeechEngine] SAPI SpVoice directo no disponible: {e}")

        engine = None
        if not sp_voice:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', 160)
                print("[SpeechEngine] pyttsx3 activado.")
            except Exception as e:
                print(f"[SpeechEngine] pyttsx3 no disponible: {e}")

        while True:
            try:
                texto = self._cola_tts.get()
                if texto is None:
                    break
                
                texto_str = str(texto).strip()
                if not texto_str:
                    self._cola_tts.task_done()
                    continue

                # Marcar que la app está hablando para silenciar el micrófono y romper bucles de eco
                self.reproduciendo_tts = True

                if sp_voice:
                    sp_voice.Speak(texto_str)
                elif engine:
                    engine.say(texto_str)
                    engine.runAndWait()
                else:
                    import subprocess
                    txt_clean = texto_str.replace("'", " ").replace('"', " ")
                    subprocess.run(
                        f'PowerShell -Command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak(\'{txt_clean}\')"',
                        shell=True
                    )

                # Pausa breve para disipar el eco del parlante en la habitación
                time.sleep(0.4)
                if self.reconocedor_vosk:
                    try:
                        self.reconocedor_vosk.Result()  # Descartar cualquier audio captado durante la locución
                    except Exception:
                        pass
                self.reproduciendo_tts = False
                self._cola_tts.task_done()
            except Exception as e:
                print(f"[SpeechEngine] Error al reproducir audio TTS en PC: {e}")
                self.reproduciendo_tts = False

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

    def hablar(self, texto, reintentos=3):
        """Convierte texto a voz mediante el motor nativo de Android o SAPI5/pyttsx3 en PC."""
        print(f"[TTS Audio Output]: {texto}")
        if self.tts:
            if not getattr(self, 'tts_listo', False) and reintentos > 0:
                print(f"[SpeechEngine Android] Esperando inicialización de TTS nativo... Reintentando en 0.6s ({reintentos})")
                Clock.schedule_once(lambda dt: self.hablar(texto, reintentos - 1), 0.6)
                return

            # ANTI-ECO: Detener el micrófono ANTES de reproducir audio para evitar que el SpeechRecognizer
            # capture la voz del propio asistente y genere un bucle.
            self.reproduciendo_tts = True
            self._detener_speech_recognizer_android()

            try:
                from jnius import autoclass
                Locale = autoclass('java.util.Locale')
                try:
                    self.tts.setLanguage(Locale("es", "ES"))
                except Exception:
                    pass

                # En Android, QUEUE_FLUSH = 0
                res = -1
                try:
                    res = self.tts.speak(texto, 0, None, "baston_tts")
                except Exception:
                    try:
                        res = self.tts.speak(texto, 0, None)
                    except Exception as e2:
                        print(f"[SpeechEngine Android] Error en speak legacy: {e2}")

                if res == 0:
                    # Iniciar monitoreo de fin de locución mediante tts.isSpeaking()
                    Clock.schedule_once(lambda dt: self._esperar_fin_tts_android(), 0.4)
                elif reintentos > 0:
                    print(f"[SpeechEngine Android] speak devolvio codigo {res}. Reintentando en 0.6s...")
                    self.reproduciendo_tts = False
                    Clock.schedule_once(lambda dt: self.hablar(texto, reintentos - 1), 0.6)
                else:
                    self.reproduciendo_tts = False
            except Exception as e:
                print(f"[SpeechEngine Android] Error al reproducir TTS: {e}")
                self.reproduciendo_tts = False
        else:
            self._cola_tts.put(texto)

    def _esperar_fin_tts_android(self, contador_max=40):
        """Monitorea tts.isSpeaking() hasta que termine la locución y reactiva el micrófono."""
        try:
            hablando = False
            if self.tts and hasattr(self.tts, 'isSpeaking'):
                hablando = bool(self.tts.isSpeaking())

            if hablando and contador_max > 0:
                Clock.schedule_once(lambda dt: self._esperar_fin_tts_android(contador_max - 1), 0.3)
            else:
                # Locución finalizada: esperar 0.5s para disipar eco y reactivar micrófono
                print("[SpeechEngine Android] Locución finalizada.")
                def reactivar_mic(dt):
                    self.reproduciendo_tts = False
                    if self.escuchando:
                        self._reiniciar_escucha_android()
                Clock.schedule_once(reactivar_mic, 0.5)
        except Exception as e:
            print(f"[SpeechEngine Android] Error al verificar isSpeaking: {e}")
            self.reproduciendo_tts = False

    def _detener_speech_recognizer_android(self):
        """Detiene el SpeechRecognizer de Android para evitar que el micrófono capture el audio del TTS."""
        try:
            if not hasattr(self, 'speech_rec') or not self.speech_rec:
                return
            from jnius import autoclass, PythonJavaClass, java_method
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            class Runnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                def __init__(self, func):
                    super().__init__()
                    self.func = func
                @java_method('()V')
                def run(self):
                    self.func()

            def parar():
                try:
                    self.speech_rec.stopListening()
                except Exception as ex:
                    print(f"[SpeechEngine] stopListening error: {ex}")

            PythonActivity.mActivity.runOnUiThread(Runnable(parar))
        except Exception as e:
            print(f"[SpeechEngine] _detener_speech_recognizer_android error: {e}")




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
        """Usa SpeechRecognizer nativo en Android o PyAudio/Vosk + Consola en PC."""
        if self.activity:
            self._iniciar_reconocimiento_nativo_android(callback_comando, callback_parcial)
        else:
            # En PC: Iniciar micrófono en hilo secundario para no bloquear el teclado
            if self.reconocedor_vosk:
                hilo_mic = threading.Thread(
                    target=self._grabar_audio_desktop,
                    args=(callback_comando, callback_parcial),
                    daemon=True
                )
                hilo_mic.start()
                print("[SpeechEngine] Micrófono Vosk activo en segundo plano.")
            
            # Entrada por teclado en la consola de la PC (garantizado para desarrollo y pruebas)
            self._simular_escucha_continua(callback_comando)


    def solicitar_voz_android(self):
        """Dispara el diálogo nativo de voz de Android con micrófono en pantalla (100% garantizado)."""
        if self.activity:
            try:
                from jnius import autoclass
                Intent = autoclass('android.content.Intent')
                RecognizerIntent = autoclass('android.speech.RecognizerIntent')
                
                intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es")
                intent.putExtra(RecognizerIntent.EXTRA_PROMPT, f"Di tu comando o 'Hola {self.nombre_asistente.capitalize()}'...")
                
                self.activity.startActivityForResult(intent, 1001)
                print("[SpeechEngine] Intent nativo de escucha por voz iniciado.")
            except Exception as e:
                print(f"[SpeechEngine] Error al iniciar voz por Intent: {e}")

    def _iniciar_reconocimiento_nativo_android(self, callback_comando, callback_parcial=None):
        """Inicia el reconocedor de voz nativo de Android en el Looper del Hilo UI."""
        try:
            if not self.escuchando:
                return

            if getattr(self, 'reproduciendo_tts', False):
                Clock.schedule_once(
                    lambda dt: self._iniciar_reconocimiento_nativo_android(callback_comando, callback_parcial),
                    0.6
                )
                return

            from jnius import autoclass, PythonJavaClass, java_method
            
            SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
            Intent = autoclass('android.content.Intent')
            RecognizerIntent = autoclass('android.speech.RecognizerIntent')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            class Runnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                def __init__(self, func):
                    super().__init__()
                    self.func = func
                @java_method('()V')
                def run(self):
                    self.func()

            class EscuchadorAndroid(PythonJavaClass):
                __javainterfaces__ = ['android/speech/RecognitionListener']

                def __init__(self, engine, callback_cmd, callback_prc):
                    super().__init__()
                    self.engine = engine
                    self.callback_cmd = callback_cmd
                    self.callback_prc = callback_prc

                @java_method('(Landroid/os/Bundle;)V')
                def onReadyForSpeech(self, params):
                    self.engine._errores_mic_consecutivos = 0
                    self.engine._ultimo_texto_parcial = ""
                    print("[SpeechRecognizer Android] Micrófono listo.")

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
                    """
                    Códigos comunes de Android SpeechRecognizer:
                      1=NETWORK_TIMEOUT  2=NETWORK  3=AUDIO  4=SERVER
                      5=CLIENT          6=SPEECH_TIMEOUT  7=NO_MATCH
                      8=RECOGNIZER_BUSY  9=INSUFFICIENT_PERMISSIONS
                    """
                    print(f"[SpeechRecognizer] Evento micrófono código {error}.")

                    if not self.engine.escuchando or getattr(self.engine, 'reproduciendo_tts', False):
                        return  # No reiniciar si el TTS está hablando

                    if error == 9:
                        self.engine.escuchando = False
                        print("[SpeechRecognizer] Permiso de micrófono insuficiente. Escucha detenida.")
                        return

                    parcial = getattr(self.engine, '_ultimo_texto_parcial', '').strip()
                    if parcial and error in [6, 7]:
                        print(f"[SpeechRecognizer Parcial usado]: '{parcial}'")
                        self.engine._procesar_texto_reconocido(parcial, self.callback_cmd)
                        self.engine._ultimo_texto_parcial = ""

                    if self.engine._evento_reinicio_mic is not None:
                        try:
                            self.engine._evento_reinicio_mic.cancel()
                        except Exception:
                            pass
                        self.engine._evento_reinicio_mic = None

                    self.engine._errores_mic_consecutivos += 1
                    extra = min(self.engine._errores_mic_consecutivos * 0.4, 4.0)

                    # Errores 6 (SPEECH_TIMEOUT) y 7 (NO_MATCH) son normales cuando nadie habla.
                    # Se reinicia con una pausa breve para que Android no quede en RECOGNIZER_BUSY.
                    if error in [6, 7]:
                        retardo = 1.2 + extra
                    elif error == 8:   # RECOGNIZER_BUSY
                        retardo = 3.0 + extra
                    else:
                        retardo = 2.0 + extra

                    self.engine._evento_reinicio_mic = Clock.schedule_once(
                        lambda dt: self.engine._reiniciar_escucha_android(), retardo
                    )

                @java_method('(Landroid/os/Bundle;)V')
                def onResults(self, results):
                    try:
                        matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        if matches and matches.size() > 0:
                            texto = str(matches.get(0)).strip()
                            print(f"[SpeechRecognizer Texto]: '{texto}'")
                            self.engine._errores_mic_consecutivos = 0
                            self.engine._ultimo_texto_parcial = ""
                            self.engine._procesar_texto_reconocido(texto, self.callback_cmd)
                    except Exception as e:
                        print(f"[SpeechRecognizer Error Resultados]: {e}")
                    
                    # Reinicio rápido tras procesar el resultado de voz
                    if self.engine.escuchando and not getattr(self.engine, 'reproduciendo_tts', False):
                        if self.engine._evento_reinicio_mic is not None:
                            try:
                                self.engine._evento_reinicio_mic.cancel()
                            except Exception:
                                pass
                        self.engine._evento_reinicio_mic = Clock.schedule_once(
                            lambda dt: self.engine._reiniciar_escucha_android(), 0.8
                        )

                @java_method('(Landroid/os/Bundle;)V')
                def onPartialResults(self, partialResults):
                    try:
                        matches = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        if matches and matches.size() > 0 and self.callback_prc:
                            parcial = str(matches.get(0)).strip()
                            if parcial:
                                self.engine._ultimo_texto_parcial = parcial
                                Clock.schedule_once(lambda dt, p=parcial: self.callback_prc(p), 0)
                    except Exception:
                        pass

                @java_method('(ILandroid/os/Bundle;)V')
                def onEvent(self, eventType, params):
                    pass

            self.escuchador_listener = EscuchadorAndroid(self, callback_comando, callback_parcial)
            
            def accion_ui():
                try:
                    self.speech_rec = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
                    self.speech_rec.setRecognitionListener(self.escuchador_listener)

                    self.intent_escucha = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es")
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
                    try:
                        self.intent_escucha.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                        self.intent_escucha.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1200)
                        self.intent_escucha.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1600)
                        self.intent_escucha.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1200)
                    except Exception as extra_error:
                        print(f"[SpeechEngine] Extras avanzados de voz no disponibles: {extra_error}")

                    self.speech_rec.startListening(self.intent_escucha)
                    print("[SpeechEngine UI Thread] SpeechRecognizer iniciado en Hilo UI.")
                except Exception as e:
                    print(f"[SpeechEngine UI Thread Error]: {e}")


            PythonActivity.mActivity.runOnUiThread(Runnable(accion_ui))
        except Exception as e:
            print(f"[SpeechEngine Android Listener Error]: {e}")

    def _reiniciar_escucha_android(self):
        """Reanuda la escucha del mic en Android sin saturar SpeechRecognizer."""
        import time

        # Limpiar referencia al evento de Clock (ya disparó)
        self._evento_reinicio_mic = None

        if not self.escuchando or getattr(self, 'reproduciendo_tts', False):
            print("[SpeechEngine] Reinicio del mic cancelado: TTS activo o escucha detenida.")
            return

        if getattr(self, '_reiniciando_mic', False):
            print("[SpeechEngine] Reinicio del mic ignorado: ya hay uno en curso.")
            return

        # Android no soporta una sesión infinita real; este margen evita RECOGNIZER_BUSY.
        MIN_INTERVALO_REINICIO = 1.2
        ahora = time.time()
        tiempo_transcurrido = ahora - getattr(self, '_ultimo_reinicio_mic', 0)
        if tiempo_transcurrido < MIN_INTERVALO_REINICIO:
            espera = MIN_INTERVALO_REINICIO - tiempo_transcurrido
            print(f"[SpeechEngine] Reinicio demasiado rápido ({tiempo_transcurrido:.1f}s). Esperando {espera:.1f}s más.")
            self._evento_reinicio_mic = Clock.schedule_once(
                lambda dt: self._reiniciar_escucha_android(), espera
            )
            return

        self._reiniciando_mic = True
        self._ultimo_reinicio_mic = ahora

        try:
            from jnius import autoclass, PythonJavaClass, java_method
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            class Runnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                def __init__(self, func):
                    super().__init__()
                    self.func = func
                @java_method('()V')
                def run(self):
                    self.func()

            def reanudar():
                try:
                    SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
                    if hasattr(self, 'speech_rec') and self.speech_rec:
                        try:
                            self.speech_rec.cancel()
                        except Exception:
                            pass
                        try:
                            self.speech_rec.destroy()
                        except Exception:
                            pass
                        self.speech_rec = None

                    if hasattr(self, 'intent_escucha') and hasattr(self, 'escuchador_listener'):
                        self.speech_rec = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
                        self.speech_rec.setRecognitionListener(self.escuchador_listener)
                        self.speech_rec.startListening(self.intent_escucha)
                        print("[SpeechEngine] Micrófono recreado y reiniciado correctamente.")
                except Exception as ex:
                    print(f"[SpeechEngine] startListening error: {ex}")
                finally:
                    self._reiniciando_mic = False

            PythonActivity.mActivity.runOnUiThread(Runnable(reanudar))
        except Exception as e:
            print(f"[SpeechEngine Android Error Reanudar]: {e}")
            self._reiniciando_mic = False



    def _grabar_audio_desktop(self, callback_comando, callback_parcial):
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)
            stream.start_stream()
            print("[SpeechEngine] Micrófono de PC escuchando en segundo plano...")
            
            while self.escuchando:
                data = stream.read(4000, exception_on_overflow=False)
                
                # Prevenir bucles de eco: si el asistente está hablando por los parlantes, ignorar el micrófono
                if self.reproduciendo_tts:
                    continue

                if self.reconocedor_vosk.AcceptWaveform(data):
                    res = json.loads(self.reconocedor_vosk.Result())
                    texto = res.get("text", "").strip()
                    if texto:
                        print(f"\n🎤 [MICRÓFONO DETECTÓ VOZ]: '{texto}'")
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
            print(f"[SpeechEngine] Aviso en captura de micrófono PC ({e}). Se usará teclado en consola.")


    def _simular_escucha_continua(self, callback_comando):
        """Modo de desarrollo en PC: acepta comandos escritos por teclado en la consola."""
        nombre = self.nombre_asistente.capitalize()
        print(f"\n{'='*60}")
        print(f"  MODO PC - ENTRADA POR TECLADO")
        print(f"  Escribe tus comandos como si hablaras.")
        print(f"  Ejemplo: 'hola' o 'dónde estoy' o 'mi agenda'")
        print(f"  Escribe 'salir' para detener.")
        print(f"{'='*60}\n")

        while self.escuchando:
            try:
                entrada = input(f"[{nombre}] Tu comando > ").strip()
                if not entrada:
                    continue
                if entrada.lower() == "salir":
                    self.escuchando = False
                    print("[SpeechEngine] Escucha detenida por el usuario.")
                    break
                print(f"[SpeechEngine - PC]: Comando recibido: '{entrada}'")
                self._procesar_texto_reconocido(entrada, callback_comando)
            except (EOFError, KeyboardInterrupt):
                self.escuchando = False
                break
            except Exception as e:
                print(f"[SpeechEngine - PC Error]: {e}")
                time.sleep(1)

    def _procesar_texto_reconocido(self, texto_completo, callback_comando):
        """Filtra y limpia el texto reconociendo por coincidencias clave sin exigir frases exactas ni nombres obligatorios."""
        if not texto_completo:
            return

        texto_norm = normalizar_texto(texto_completo)
        print(f"[SpeechEngine - Reconocido original]: '{texto_completo}'")
        print(f"[SpeechEngine - Reconocido normalizado]: '{texto_norm}'")
        if not texto_norm:
            return

        activado = False
        comando_limpio = texto_norm

        # 1. Comprobar si incluye alguna palabra de activación (ej. bastón, rayo, oye bastón)
        for palabra in self.palabras_activacion:
            palabra_norm = normalizar_texto(palabra)
            if palabra_norm and palabra_norm in texto_norm:
                activado = True
                comando_limpio = texto_norm.replace(palabra_norm, "").strip()
                break

        # 2. Búsqueda exhaustiva por coincidencias de cualquier intención
        coincidencias_clave = [
            # Visión / Obstáculos / Frente
            "frente", "delante", "adelante", "enfrente", "que hay", "que veo", "que ves", "que miras",
            "mira", "mirar", "ver", "entorno", "alrededor", "camara", "foto", "obstaculo", "obstaculos",
            "analizar", "escaneo", "escanea", "objeto", "objetos", "que tenemos",
            # Ubicación GPS
            "donde", "ubicacion", "lugar", "posicion", "direccion", "donde estoy", "donde ando", "donde encuentro",
            # Navegación
            "guiame", "guia", "llevame", "lleva", "ir a", "ir al", "ir a la", "como llego", "navegar", "ruta", "destino", "dirigeme",
            # Cancelar
            "cancelar", "detener", "parar",
            # Lectura Documentos
            "leer", "lee", "lectura", "documento", "hoja", "etiqueta", "texto", "papel", "carta", "pagina",
            # Agenda
            "agenda", "anotar", "agendar", "recordar", "nota", "recordatorio", "recordatorios", "tarea", "tareas",
            # Bastón / Bluetooth
            "conectar", "conectate", "desconectar", "enlazar", "vincular", "bluetooth",
            # Asistente / Nombre
            "nombre", "llamarte", "llamate", "llamame", "tu nombre",
            # QR
            "qr", "codigo", "compartir", "comparte",
            # Saludo
            "hola", "saludo", "ayuda", "activado", "quien eres", "buenas", "estas ahi"
        ]

        if not activado:
            if any(kw in texto_norm for kw in coincidencias_clave):
                activado = True

        if activado:
            instruccion = comando_limpio if comando_limpio else "hola"
            Clock.schedule_once(lambda dt: callback_comando(instruccion), 0)
        else:
            # Si se escuchó algo con longitud razonable, enviarlo para dar feedback siempre
            if len(texto_norm) >= 2:
                Clock.schedule_once(lambda dt: callback_comando(texto_norm), 0)
