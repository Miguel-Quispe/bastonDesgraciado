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
        self.reproduciendo_tts = False
        self._reiniciando_mic = False
        self._ultimo_reinicio_mic = 0
        self._evento_reinicio_mic = None
        self._errores_mic_consecutivos = 0
        self._ultimo_texto_parcial = ""
        self._bloqueo_eco_hasta = 0.0
        self._ignorar_errores_hasta = 0.0
        self._escucha_una_vez = False
        self._callback_fin_escucha_una_vez = None

        # Parámetros acústicos: Perfil Optimus Prime (Voz grave, firme y profunda)
        self.archivo_config = os.path.join(os.getcwd(), "config_asistente.json")
        config = self._cargar_config()
        self.nombre_asistente = config.get("nombre", "optimus").lower().strip()
        self.velocidad_voz = float(config.get("velocidad", 0.88)) # Cadencia firme y medida
        self.tono_voz = float(config.get("tono", 0.68))            # Tono grave / robótico tipo Optimus Prime
        self.genero_voz = config.get("genero", "masculina")
        self.url_servidor_voz = config.get("url_servidor_voz", "http://192.168.1.100:5000")

        self._cola_tts = queue.Queue()
        self._hilo_tts_pc = threading.Thread(target=self._loop_tts_pc, daemon=True)
        self._hilo_tts_pc.start()

        if palabras_activacion is not None:
            self.palabras_activacion = palabras_activacion
        else:
            self._reconstruir_palabras_activacion()

        self.requiere_palabra_activacion = True
        self.ruta_modelo = ruta_modelo if os.path.isabs(ruta_modelo) else os.path.join(os.getcwd(), ruta_modelo)
        
        self._inicializar_android()
        self._inicializar_vosk()

    def _cargar_config(self):
        try:
            if os.path.exists(self.archivo_config):
                with open(self.archivo_config, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        # Por defecto configuración estilo persona animada y amigable
        return {"nombre": "asistente", "velocidad": 1.05, "tono": 1.08, "genero": "animada"}

    def _guardar_config(self):
        try:
            datos = {
                "nombre": self.nombre_asistente,
                "velocidad": self.velocidad_voz,
                "tono": self.tono_voz,
                "genero": self.genero_voz
            }
            with open(self.archivo_config, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SpeechEngine] Error guardando config: {e}")

    def cambiar_velocidad(self, delta):
        """Aumenta o disminuye la velocidad de la voz."""
        nueva_vel = max(0.85, min(1.3, self.velocidad_voz + delta))
        self.velocidad_voz = round(nueva_vel, 2)
        self._guardar_config()
        self._aplicar_parametros_tts_android()
        modo = "rápido" if delta > 0 else "pausado"
        self.hablar(f"Velocidad ajustada a ritmo {modo}.", perfil="animada")

    def cambiar_tono(self, nuevo_tono=None, modo="animada"):
        """Permite alternar entre un tono animado natural o extra vivaz."""
        if nuevo_tono is not None:
            self.tono_voz = float(nuevo_tono)
        else:
            if self.tono_voz < 1.10:
                self.tono_voz = 1.12
            else:
                self.tono_voz = 1.05

        self.genero_voz = "animada"
        self._guardar_config()
        self._aplicar_parametros_tts_android()
        self.hablar("Tono de voz animado activado.", perfil="animada")

    def _reconstruir_palabras_activacion(self):
        nombre = self.nombre_asistente
        self.palabras_activacion = [
            nombre,
            "asistente",
            "copiloto",
            "amigo",
            f"oye {nombre}",
            f"hola {nombre}",
            f"ok {nombre}",
            "bastón", "baston"
        ]

    def actualizar_nombre_asistente(self, nuevo_nombre):
        nombre_limpio = nuevo_nombre.lower().strip()
        if not nombre_limpio:
            return

        self.nombre_asistente = nombre_limpio
        self._reconstruir_palabras_activacion()
        self._guardar_config()
        self.hablar(f"Identidad actualizada a {self.nombre_asistente.capitalize()}. ¡Listo para ayudarte!", perfil="animada")

    def _aplicar_parametros_tts_android(self, perfil="animada"):
        """Aplica la velocidad, tono e idioma en el motor nativo de Android con estilo de persona animada."""
        if not self.tts or not getattr(self, 'tts_listo', False):
            return
        try:
            if perfil == "alerta":
                # Alerta rápida y clara del sensor
                pitch = 1.18
                rate = 1.15
            else:
                # Voz de persona animada, alegre, natural y cordial
                pitch = 1.08
                rate = 1.05

            self.tts.setPitch(pitch)
            self.tts.setSpeechRate(rate)

            # Asignar la mejor voz fluida en español de Google / Android
            try:
                voices = self.tts.getVoices()
                if voices:
                    iterator = voices.iterator()
                    while iterator.hasNext():
                        voice = iterator.next()
                        nombre_v = voice.getName().lower()
                        locale_v = voice.getLocale().getLanguage()
                        if locale_v == "es":
                            # Priorizar voces animadas, claras y naturales
                            if any(k in nombre_v for k in ["natural", "neural", "es-es-x-ana", "es-us-x-sfd", "female", "ana", "es-es"]):
                                self.tts.setVoice(voice)
                                break
            except Exception:
                pass
        except Exception as e:
            print(f"[SpeechEngine] Aviso al aplicar parámetros TTS ({perfil}): {e}")

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
                    if status == 0:
                        self.engine.tts_listo = True
                        try:
                            Locale = autoclass('java.util.Locale')
                            self.engine.tts.setLanguage(Locale("es", "ES"))
                        except Exception:
                            pass
                        self.engine._configurar_listener_fin_locucion()
                        self.engine._aplicar_parametros_tts_android()

            self.tts_listener = TTSInitListener(self)
            self.tts = self.TextToSpeech(self.activity, self.tts_listener)
        except Exception:
            self.tts = None
            self.tts_listo = False

    def _configurar_listener_fin_locucion(self):
        """Usa UtteranceProgressListener para saber EXACTAMENTE cuándo termina de hablar y no cortar la frase."""
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            
            class FinLocucionListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/tts/UtteranceProgressListener']
                def __init__(self, engine):
                    super().__init__()
                    self.engine = engine

                @java_method('(Ljava/lang/String;)V')
                def onStart(self, utteranceId):
                    self.engine.reproduciendo_tts = True

                @java_method('(Ljava/lang/String;)V')
                def onDone(self, utteranceId):
                    def al_completar(dt):
                        self.engine.reproduciendo_tts = False
                        if self.engine.escuchando:
                            self.engine._reiniciar_escucha_android()
                    Clock.schedule_once(al_completar, 0.4)

                @java_method('(Ljava/lang/String;)V')
                def onError(self, utteranceId):
                    def al_error(dt):
                        self.engine.reproduciendo_tts = False
                    Clock.schedule_once(al_error, 0.2)

            self.tts_progress_listener = FinLocucionListener(self)
            self.tts.setOnUtteranceProgressListener(self.tts_progress_listener)
        except Exception as e:
            print(f"[SpeechEngine] UtteranceProgressListener no disponible: {e}")

    def _loop_tts_pc(self):
        sp_voice = None
        try:
            import comtypes.client
            sp_voice = comtypes.client.CreateObject("SAPI.SpVoice")
            sp_voice.Rate = -2 # Ritmo pausado estilo Optimus
        except Exception:
            pass

        engine = None
        if not sp_voice:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', 145)
            except Exception:
                pass

        while True:
            try:
                elemento = self._cola_tts.get()
                if elemento is None:
                    break

                if isinstance(elemento, tuple):
                    texto_item, perfil_item = elemento
                else:
                    texto_item, perfil_item = elemento, "normal"

                texto_str = str(texto_item).strip()
                if not texto_str:
                    self._cola_tts.task_done()
                    continue

                self.reproduciendo_tts = True

                rate_pc = 1
                if perfil_item == "alerta":
                    rate_pc = 2
                elif perfil_item in ("animada", "ia", "normal"):
                    rate_pc = 1

                if sp_voice:
                    try:
                        sp_voice.Rate = rate_pc
                    except Exception:
                        pass
                    sp_voice.Speak(texto_str)
                elif engine:
                    try:
                        engine.setProperty('rate', 190 if perfil_item == "alerta" else 165)
                    except Exception:
                        pass
                    engine.say(texto_str)
                    engine.runAndWait()
                else:
                    import subprocess
                    txt_clean = texto_str.replace("'", " ").replace('"', " ")
                    subprocess.run(
                        f'PowerShell -Command "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate = {rate_pc}; $s.Speak(\'{txt_clean}\')"',
                        shell=True
                    )

                time.sleep(0.4)
                if self.reconocedor_vosk:
                    try:
                        self.reconocedor_vosk.Result()
                    except Exception:
                        pass
                self.reproduciendo_tts = False
                self._cola_tts.task_done()
            except Exception:
                self.reproduciendo_tts = False

    def _inicializar_vosk(self):
        try:
            from vosk import Model, KaldiRecognizer
            if os.path.exists(self.ruta_modelo):
                self.modelo_vosk = Model(self.ruta_modelo)
                self.reconocedor_vosk = KaldiRecognizer(self.modelo_vosk, 16000)
        except Exception:
            pass

    def hablar(self, texto, reintentos=3, perfil="normal"):
        """Convierte texto a voz completo según el perfil acústico (alerta o Optimus Prime) sin cortes."""
        etiqueta = "ALERTA SENSOR" if perfil == "alerta" else "OPTIMUS PRIME"
        print(f"[{etiqueta}]: {texto}")
        if not texto:
            return

        if self.tts:
            if not getattr(self, 'tts_listo', False) and reintentos > 0:
                Clock.schedule_once(lambda dt: self.hablar(texto, reintentos - 1, perfil=perfil), 0.5)
                return

            self.reproduciendo_tts = True
            duracion_estimada = max(3.5, (len(str(texto)) / 8.5) + 2.0)
            self._bloqueo_eco_hasta = max(self._bloqueo_eco_hasta, time.monotonic() + duracion_estimada)
            self._detener_speech_recognizer_android()

            try:
                from jnius import autoclass
                Locale = autoclass('java.util.Locale')
                try:
                    self.tts.setLanguage(Locale("es", "ES"))
                except Exception:
                    pass

                self._aplicar_parametros_tts_android(perfil=perfil)

                utterance_id = f"voz_{perfil}_{int(time.time() * 1000)}"
                res = -1
                try:
                    res = self.tts.speak(texto, 0, None, utterance_id)
                except Exception:
                    try:
                        res = self.tts.speak(texto, 0, None)
                    except Exception:
                        pass

                if res != 0 and reintentos > 0:
                    self.reproduciendo_tts = False
                    Clock.schedule_once(lambda dt: self.hablar(texto, reintentos - 1, perfil=perfil), 0.5)
            except Exception:
                self.reproduciendo_tts = False
        else:
            self._cola_tts.put((texto, perfil))

    def hablar_alerta(self, texto):
        """Perfil Sensor/Bastón: Tono agudo y cadencia rápida para avisos inmediatos del sensor."""
        Clock.schedule_once(lambda dt: self.hablar(texto, perfil="alerta"), 0)

    def hablar_respuesta_ia(self, texto, callback_fin=None):
        """Voz animada, natural, alegre y cordial para las respuestas de la IA."""
        if not texto:
            return

        # Respuesta nativa inmediata con perfil animado
        Clock.schedule_once(lambda dt: self.hablar(texto, perfil="animada"), 0)

    def _obtener_audio_clonado_servidor(self, texto):
        """Envía el texto al servidor XTTS con la muestra optimus_muestra.wav de Blas García."""
        if not getattr(self, 'url_servidor_voz', None):
            return None
        try:
            import requests
            url = f"{self.url_servidor_voz.rstrip('/')}/sintetizar"
            resp = requests.post(url, json={"texto": texto}, timeout=6.0)
            if resp.status_code == 200 and len(resp.content) > 1000:
                ruta_salida = os.path.join(os.getcwd(), "respuesta_optimus_ia.wav")
                with open(ruta_salida, "wb") as f:
                    f.write(resp.content)
                return ruta_salida
        except Exception as e:
            print(f"[SpeechEngine] Servidor XTTS no disponible ({e}). Usando fallback nativo.")
        return None

    def reproducir_audio(self, ruta_audio, callback_fin=None):
        """Reproduce un archivo de audio local (.wav/.mp3) con la voz auténtica en Android o PC."""
        if not os.path.exists(ruta_audio):
            return

        self.reproduciendo_tts = True
        self._detener_speech_recognizer_android()

        # 1. En Android mediante MediaPlayer nativo
        if self.activity:
            try:
                from jnius import autoclass, PythonJavaClass, java_method
                MediaPlayer = autoclass('android.media.MediaPlayer')
                player = MediaPlayer()
                player.setDataSource(ruta_audio)
                player.prepare()

                class AudioEndListener(PythonJavaClass):
                    __javainterfaces__ = ['android/media/MediaPlayer$OnCompletionListener']
                    def __init__(self, engine, cb):
                        super().__init__()
                        self.engine = engine
                        self.cb = cb

                    @java_method('(Landroid/media/MediaPlayer;)V')
                    def onCompletion(self, mp):
                        mp.release()
                        def al_terminar(dt):
                            self.engine.reproduciendo_tts = False
                            if self.cb:
                                self.cb()
                            if self.engine.escuchando:
                                self.engine._reiniciar_escucha_android()
                        Clock.schedule_once(al_terminar, 0.3)

                player.setOnCompletionListener(AudioEndListener(self, callback_fin))
                player.start()
                return
            except Exception as e:
                print(f"[SpeechEngine] Error al reproducir audio en Android: {e}")

        # 2. En PC mediante SoundLoader de Kivy
        try:
            from kivy.core.audio import SoundLoader
            sonido = SoundLoader.load(ruta_audio)
            if sonido:
                def al_detener_sonido():
                    self.reproduciendo_tts = False
                    if callback_fin:
                        callback_fin()
                sonido.bind(on_stop=lambda s: Clock.schedule_once(lambda dt: al_detener_sonido(), 0.3))
                sonido.play()
                return
        except Exception as e:
            print(f"[SpeechEngine] Error SoundLoader en PC: {e}")

        self.reproduciendo_tts = False

    def _detener_speech_recognizer_android(self):
        try:
            self._ignorar_errores_hasta = time.monotonic() + 1.2
            if self._evento_reinicio_mic is not None:
                try:
                    self._evento_reinicio_mic.cancel()
                except Exception:
                    pass
                self._evento_reinicio_mic = None
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
                    if self.speech_rec:
                        self.speech_rec.cancel()
                        self.speech_rec.destroy()
                except Exception:
                    pass
                self.speech_rec = None

            PythonActivity.mActivity.runOnUiThread(Runnable(parar))
        except Exception:
            pass

    def iniciar_escucha_continua(self, callback_comando, callback_parcial=None):
        if self.escuchando:
            return
        self.escuchando = True
        self.hilo_escucha = threading.Thread(
            target=self._loop_escucha_continua, 
            args=(callback_comando, callback_parcial),
            daemon=True
        )
        self.hilo_escucha.start()

    def detener_escucha(self):
        self.escuchando = False

    def escuchar_una_vez(self, callback_comando, callback_finalizar=None):
        """Detiene locuciones previas, prepara el micro y escucha un comando único."""
        self.detener_voz()
        if self._evento_reinicio_mic is not None:
            try:
                self._evento_reinicio_mic.cancel()
            except Exception:
                pass
            self._evento_reinicio_mic = None
        self._escucha_una_vez = True
        self._callback_fin_escucha_una_vez = callback_finalizar
        self.escuchando = True
        if self.activity:
            self._iniciar_reconocimiento_nativo_android(callback_comando)
        else:
            self._escucha_una_vez = False
            self.iniciar_escucha_continua(callback_comando)
        return True

    def _finalizar_escucha_una_vez(self):
        if not self._escucha_una_vez:
            return
        self.escuchando = False
        self._escucha_una_vez = False
        self._detener_speech_recognizer_android()
        callback = self._callback_fin_escucha_una_vez
        self._callback_fin_escucha_una_vez = None
        if callback:
            Clock.schedule_once(lambda dt: callback(), 0.1)

    def _loop_escucha_continua(self, callback_comando, callback_parcial):
        if self.activity:
            self._iniciar_reconocimiento_nativo_android(callback_comando, callback_parcial)
        else:
            if self.reconocedor_vosk:
                hilo_mic = threading.Thread(
                    target=self._grabar_audio_desktop,
                    args=(callback_comando, callback_parcial),
                    daemon=True
                )
                hilo_mic.start()
            self._simular_escucha_continua(callback_comando)

    def _iniciar_reconocimiento_nativo_android(self, callback_comando, callback_parcial=None):
        try:
            if not self.escuchando:
                return

            if getattr(self, 'reproduciendo_tts', False):
                Clock.schedule_once(
                    lambda dt: self._iniciar_reconocimiento_nativo_android(callback_comando, callback_parcial),
                    0.8
                )
                return

            espera_eco = self._bloqueo_eco_hasta - time.monotonic()
            if espera_eco > 0:
                Clock.schedule_once(
                    lambda dt: self._iniciar_reconocimiento_nativo_android(callback_comando, callback_parcial),
                    espera_eco
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
                    if time.monotonic() < getattr(self.engine, '_ignorar_errores_hasta', 0):
                        return

                    if not self.engine.escuchando or getattr(self.engine, 'reproduciendo_tts', False):
                        return

                    if self.engine._escucha_una_vez:
                        self.engine._finalizar_escucha_una_vez()
                        return

                    if error == 9:
                        self.engine.escuchando = False
                        return

                    parcial = getattr(self.engine, '_ultimo_texto_parcial', '').strip()
                    if parcial and error in [6, 7]:
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

                    if error in [6, 7]:
                        retardo = 1.4 + extra
                    elif error == 8:
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
                            self.engine._errores_mic_consecutivos = 0
                            self.engine._ultimo_texto_parcial = ""
                            self.engine._procesar_texto_reconocido(texto, self.callback_cmd)
                    except Exception:
                        pass
                    
                    if self.engine._escucha_una_vez:
                        self.engine._finalizar_escucha_una_vez()
                        return

                    if self.engine.escuchando and not getattr(self.engine, 'reproduciendo_tts', False):
                        if self.engine._evento_reinicio_mic is not None:
                            try:
                                self.engine._evento_reinicio_mic.cancel()
                            except Exception:
                                pass
                        self.engine._evento_reinicio_mic = Clock.schedule_once(
                            lambda dt: self.engine._reiniciar_escucha_android(), 1.6
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
                    if hasattr(self, 'speech_rec') and self.speech_rec:
                        try:
                            self.speech_rec.cancel()
                            self.speech_rec.destroy()
                        except Exception:
                            pass
                        self.speech_rec = None
                    if not SpeechRecognizer.isRecognitionAvailable(PythonActivity.mActivity):
                        print("[SpeechEngine] Reconocimiento de voz no disponible en el dispositivo.")
                        if self._escucha_una_vez:
                            self._finalizar_escucha_una_vez()
                        return
                    self.speech_rec = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
                    if not self.speech_rec:
                        print("[SpeechEngine] No se pudo instanciar SpeechRecognizer.")
                        if self._escucha_una_vez:
                            self._finalizar_escucha_una_vez()
                        return
                    self.speech_rec.setRecognitionListener(self.escuchador_listener)

                    self.intent_escucha = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-419")
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
                    self.intent_escucha.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                    self.speech_rec.startListening(self.intent_escucha)
                except Exception as e:
                    print(f"[SpeechEngine Error startListening]: {e}")
                    if self._escucha_una_vez:
                        self._finalizar_escucha_una_vez()

            PythonActivity.mActivity.runOnUiThread(Runnable(accion_ui))
        except Exception as e:
            print(f"[SpeechEngine Listener Error]: {e}")

    def _reiniciar_escucha_android(self):
        self._evento_reinicio_mic = None

        if not self.escuchando or getattr(self, 'reproduciendo_tts', False):
            return

        espera_eco = self._bloqueo_eco_hasta - time.monotonic()
        if espera_eco > 0:
            self._evento_reinicio_mic = Clock.schedule_once(
                lambda dt: self._reiniciar_escucha_android(), espera_eco
            )
            return

        if getattr(self, '_reiniciando_mic', False):
            return

        MIN_INTERVALO_REINICIO = 2.0
        ahora = time.time()
        tiempo_transcurrido = ahora - getattr(self, '_ultimo_reinicio_mic', 0)
        if tiempo_transcurrido < MIN_INTERVALO_REINICIO:
            espera = MIN_INTERVALO_REINICIO - tiempo_transcurrido
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

                    if hasattr(self, 'intent_escucha') and hasattr(self, 'escuchador_listener'):
                        if not self.speech_rec:
                            self.speech_rec = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
                            self.speech_rec.setRecognitionListener(self.escuchador_listener)
                        self.speech_rec.startListening(self.intent_escucha)
                except Exception as ex:
                    print(f"[SpeechEngine] Error reanudando: {ex}")
                finally:
                    self._reiniciando_mic = False

            PythonActivity.mActivity.runOnUiThread(Runnable(reanudar))
        except Exception:
            self._reiniciando_mic = False

    def _grabar_audio_desktop(self, callback_comando, callback_parcial):
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)
            stream.start_stream()
            
            while self.escuchando:
                data = stream.read(4000, exception_on_overflow=False)
                if self.reproduciendo_tts:
                    continue

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
        except Exception:
            pass

    def _simular_escucha_continua(self, callback_comando):
        nombre = self.nombre_asistente.capitalize()
        while self.escuchando:
            try:
                entrada = input(f"[{nombre}] Tu comando > ").strip()
                if not entrada:
                    continue
                if entrada.lower() == "salir":
                    self.escuchando = False
                    break
                self._procesar_texto_reconocido(entrada, callback_comando)
            except (EOFError, KeyboardInterrupt):
                self.escuchando = False
                break
            except Exception:
                time.sleep(1)

    def _procesar_texto_reconocido(self, texto_completo, callback_comando):
        if not texto_completo:
            return

        texto_norm = normalizar_texto(texto_completo)
        if not texto_norm:
            return

        activado = False
        comando_limpio = texto_norm

        for palabra in self.palabras_activacion:
            palabra_norm = normalizar_texto(palabra)
            if palabra_norm and palabra_norm in texto_norm:
                activado = True
                comando_limpio = texto_norm.replace(palabra_norm, "").strip()
                break

        coincidencias_clave = [
            "frente", "al frente", "alfrente", "delante", "adelante", "enfrente", "que hay", "que veo", "que ves",
            "que esta", "que tengo", "que hay al frente", "que tengo al frente", "mira", "mirar", "ver", "entorno",
            "donde", "ubicacion", "lugar", "posicion", "direccion", "donde estoy", "donde ando", "donde encuentro",
            "guiame", "guia", "llevame", "lleva", "ir a", "ir al", "ir a la", "como llego", "navegar", "ruta", "destino",
            "farmacia", "hospital", "banco", "parque",
            "cancelar", "detener", "parar", "cancelar ruta", "cancelar navegacion", "detener guia", "cancela", "para",
            "leer", "lee", "lectura", "documento", "hoja", "etiqueta", "texto",
            "agenda", "anotar", "agendar", "recordar", "nota", "recordatorio",
            "conectar", "conectate", "desconectar", "enlazar", "vincular", "bluetooth",
            "nombre", "llamarte", "llamate",
            "bateria", "carga", "pila",
            "mas lento", "mas rapido", "cambiar voz", "optimus", "optimus prime",
            "qr", "codigo", "compartir",
            "hola", "saludo", "ayuda", "quien eres", "buenas", "estas ahi"
        ]

        if not activado:
            if any(kw in texto_norm for kw in coincidencias_clave):
                activado = True

        if activado:
            instruccion = comando_limpio if comando_limpio else "hola"
            Clock.schedule_once(lambda dt: callback_comando(instruccion), 0)
        else:
            if len(texto_norm) >= 2:
                Clock.schedule_once(lambda dt: callback_comando(texto_norm), 0)
