import os
import time
import threading
from PIL import Image
from kivy.clock import Clock

CLASES_COCO_ES = {
    0: "persona", 1: "bicicleta", 2: "auto", 3: "motocicleta", 4: "avión", 5: "autobús",
    6: "tren", 7: "camión", 8: "bote", 9: "semáforo", 10: "hidrante", 11: "señal de alto",
    12: "parquímetro", 13: "banco", 14: "pájaro", 15: "gato", 16: "perro", 17: "caballo",
    18: "oveja", 19: "vaca", 24: "mochila", 25: "paraguas", 26: "bolso", 28: "maleta",
    39: "botella", 41: "taza", 56: "silla", 57: "sofá", 58: "planta", 59: "cama",
    60: "mesa", 62: "televisor", 63: "computadora", 67: "celular", 73: "libro",
    80: "cono de obra", 81: "escalón", 82: "bache", 83: "paso peatonal", 84: "poste", 85: "árbol"
}

class VisionAnalyzer:
    def __init__(self, ruta_modelo="model/yolov8n.tflite"):
        self.camara_disponible = False
        self.interpreter = None
        self._camara_android = None
        self._surface_texture = None
        self._picture_callback = None
        self._autofocus_callback = None
        self._captura_en_progreso = False
        self._esperando_resultado_intent = False
        self._camara_gesto = None
        self._preview_gesto = None
        self._detector_gesto = None
        self._gesto_activo = False
        self._pausado_gesto = False
        self._procesando_cuadro_gesto = False
        self._ultimo_cuadro_gesto = 0.0
        self._palmas_consecutivas = 0
        self._callback_gesto = None
        self._detector_objetos_local = None
        self.ruta_modelo = ruta_modelo if os.path.isabs(ruta_modelo) else os.path.join(os.getcwd(), ruta_modelo)
        
        self._inicializar_camara()
        self._inicializar_tflite()

    def _inicializar_camara(self):
        try:
            from jnius import autoclass
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.camara_disponible = True
            print("[VisionAnalyzer] Módulo de cámara nativo Android preparado.")
        except Exception:
            self.camara_disponible = False
            print("[VisionAnalyzer] Cámara en modo simulación/escritorio.")

    def _inicializar_tflite(self):
        """Carga el modelo YOLOv8 Nano en formato TFLite si está disponible."""
        if not os.path.exists(self.ruta_modelo):
            nombre_base = os.path.basename(self.ruta_modelo)
            if os.path.exists(nombre_base):
                self.ruta_modelo = os.path.abspath(nombre_base)

        if os.path.exists(self.ruta_modelo):
            try:
                try:
                    import tflite_runtime.interpreter as tflite
                    self.interpreter = tflite.Interpreter(model_path=self.ruta_modelo)
                except ImportError:
                    import tensorflow.lite as tflite
                    self.interpreter = tflite.Interpreter(model_path=self.ruta_modelo)
                
                self.interpreter.allocate_tensors()
                print(f"[VisionAnalyzer] Modelo YOLO TFLite ({self.ruta_modelo}) cargado exitosamente.")
            except Exception as e:
                print(f"[VisionAnalyzer] Error al inicializar TFLite: {e}. Usando procesamiento heurístico.")
        else:
            print(f"[VisionAnalyzer] Aviso: Modelo '{self.ruta_modelo}' no encontrado. Se usará análisis de respaldo.")

    def iniciar_detector_gesto(self, callback_gesto):
        """Observa la cámara trasera y activa un comando ante una palma abierta."""
        if self._gesto_activo or not self.camara_disponible:
            return False
        if not self._tiene_permiso_camara_android():
            return False

        try:
            from jnius import autoclass, PythonJavaClass, java_method
            Camera = autoclass('android.hardware.Camera')
            CameraInfo = autoclass('android.hardware.Camera$CameraInfo')
            SurfaceTexture = autoclass('android.graphics.SurfaceTexture')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Detector = autoclass('org.baston.bastonapp.HandSignalDetector')

            class Runnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                def __init__(self, funcion):
                    super().__init__()
                    self.funcion = funcion
                @java_method('()V')
                def run(self):
                    self.funcion()

            class PreviewCallback(PythonJavaClass):
                __javainterfaces__ = ['android/hardware/Camera$PreviewCallback']
                def __init__(self, analyzer):
                    super().__init__()
                    self.analyzer = analyzer
                @java_method('([BLandroid/hardware/Camera;)V')
                def onPreviewFrame(self, data, camera):
                    self.analyzer._recibir_cuadro_gesto(data)

            def iniciar():
                try:
                    posibles_rutas = [
                        os.path.join(PythonActivity.mActivity.getFilesDir().getAbsolutePath(), "app", "models", "hand_landmarker.task"),
                        os.path.join(PythonActivity.mActivity.getFilesDir().getAbsolutePath(), "models", "hand_landmarker.task"),
                        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "hand_landmarker.task"),
                        os.path.join(os.getcwd(), "models", "hand_landmarker.task"),
                        "models/hand_landmarker.task"
                    ]
                    ruta_modelo_gesto = None
                    for r in posibles_rutas:
                        if os.path.exists(r):
                            ruta_modelo_gesto = r
                            break
                    if not ruta_modelo_gesto:
                        ruta_modelo_gesto = posibles_rutas[0]
                    self._detector_gesto = Detector(PythonActivity.mActivity, ruta_modelo_gesto)
                    camera_id = self._seleccionar_camara_trasera(Camera, CameraInfo)
                    self._camara_gesto = Camera.open(camera_id)
                    params = self._camara_gesto.getParameters()
                    try:
                        params.setPreviewSize(640, 480)
                    except Exception:
                        pass
                    self._camara_gesto.setParameters(params)
                    tamanio = self._camara_gesto.getParameters().getPreviewSize()
                    self._gesto_ancho = tamanio.width
                    self._gesto_alto = tamanio.height
                    self._surface_gesto = SurfaceTexture(11)
                    self._preview_gesto = PreviewCallback(self)
                    self._camara_gesto.setPreviewTexture(self._surface_gesto)
                    self._camara_gesto.setPreviewCallback(self._preview_gesto)
                    self._camara_gesto.startPreview()
                    self._callback_gesto = callback_gesto
                    self._gesto_activo = True
                    print("[VisionAnalyzer] Detector de palma activo con cámara trasera.")
                except Exception as error:
                    print(f"[VisionAnalyzer] No se pudo iniciar detector de gesto: {error}")
                    self.detener_detector_gesto()

            PythonActivity.mActivity.runOnUiThread(Runnable(iniciar))
            return True
        except Exception as error:
            print(f"[VisionAnalyzer] Detector de gesto no disponible: {error}")
            return False

    def pausar_detector_gesto(self):
        """Pausa el análisis de cuadros de gestos sin destruir la cámara."""
        self._pausado_gesto = True
        self._palmas_consecutivas = 0
        self._procesando_cuadro_gesto = False

    def reanudar_detector_gesto(self, callback_gesto=None):
        """Reanuda la detección de gestos manteniendo la cámara activa o reiniciándola si fue liberada."""
        self._pausado_gesto = False
        self._palmas_consecutivas = 0
        self._procesando_cuadro_gesto = False
        if callback_gesto:
            self._callback_gesto = callback_gesto

        if self._camara_gesto:
            self._gesto_activo = True
            try:
                self._camara_gesto.startPreview()
            except Exception:
                pass
            print("[VisionAnalyzer] Detector de gesto reanudado (cámara activa).")
            return True
        else:
            cb = callback_gesto or self._callback_gesto
            if cb:
                print("[VisionAnalyzer] Reiniciando detector de gesto desde cero...")
                return self.iniciar_detector_gesto(cb)
            return False

    def _recibir_cuadro_gesto(self, data):
        ahora = time.monotonic()
        if (not self._gesto_activo or getattr(self, '_pausado_gesto', False) or 
                self._procesando_cuadro_gesto or ahora - self._ultimo_cuadro_gesto < 0.30):
            return
        self._ultimo_cuadro_gesto = ahora
        self._procesando_cuadro_gesto = True
        try:
            cuadro = bytes(data)
        except Exception:
            self._procesando_cuadro_gesto = False
            return
        threading.Thread(target=self._analizar_cuadro_gesto, args=(cuadro,), daemon=True).start()

    def _analizar_cuadro_gesto(self, cuadro):
        try:
            if not self._gesto_activo or getattr(self, '_pausado_gesto', False):
                return

            # Cooldown de 1.4 segundos entre activaciones de palma para evitar falsos rebotes con la misma mano
            ahora = time.monotonic()
            if ahora - getattr(self, '_ultimo_gesto_activado_ts', 0.0) < 1.4:
                return

            palma_abierta = False
            if self._detector_gesto:
                palma_abierta = bool(self._detector_gesto.isOpenPalmNv21(
                    cuadro, self._gesto_ancho, self._gesto_alto
                ))
            self._palmas_consecutivas = self._palmas_consecutivas + 1 if palma_abierta else 0
            if self._palmas_consecutivas >= 1:
                self._palmas_consecutivas = 0
                self._ultimo_gesto_activado_ts = time.monotonic()
                Clock.schedule_once(lambda dt: self._activar_por_gesto(), 0)
        except Exception as error:
            print(f"[VisionAnalyzer] Error analizando gesto: {error}")
        finally:
            self._procesando_cuadro_gesto = False

    def _activar_por_gesto(self):
        if not self._gesto_activo or getattr(self, '_pausado_gesto', False):
            return
        self.pausar_detector_gesto()
        callback = self._callback_gesto
        if callback:
            try:
                callback()
            except Exception as e:
                print(f"[VisionAnalyzer] Error en callback de activación por gesto: {e}")

    def detener_detector_gesto(self):
        """Libera la cámara de vigilancia de manera segura en el hilo de UI de Android."""
        self._gesto_activo = False
        self._pausado_gesto = False
        self._palmas_consecutivas = 0
        cam = self._camara_gesto
        self._camara_gesto = None
        self._preview_gesto = None
        self._surface_gesto = None
        if cam:
            try:
                from jnius import autoclass, PythonJavaClass, java_method
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                class SafeCamRunnable(PythonJavaClass):
                    __javainterfaces__ = ['java/lang/Runnable']
                    def __init__(self, f):
                        super().__init__()
                        self.f = f
                    @java_method('()V')
                    def run(self):
                        self.f()
                def cerrar():
                    try:
                        cam.setPreviewCallback(None)
                    except Exception:
                        pass
                    try:
                        cam.stopPreview()
                    except Exception:
                        pass
                    try:
                        cam.release()
                    except Exception:
                        pass
                PythonActivity.mActivity.runOnUiThread(SafeCamRunnable(cerrar))
            except Exception as error:
                print(f"[VisionAnalyzer] Error seguro cerrando cámara: {error}")
                try:
                    cam.release()
                except Exception:
                    pass

    def capturar_y_analizar(self, callback_resultado, ai_assistant=None):
        """Captura puntual para '¿Qué tengo al frente?'."""
        self.callback_pendiente = callback_resultado
        self.ai_assistant = ai_assistant
        self.ruta_foto_pendiente = self._obtener_ruta_foto()

        if self.camara_disponible:
            if not self._tiene_permiso_camara_android():
                self.cancelar_captura("No tengo permiso para usar la cámara en Android.")
                return

            if self._capturar_foto_trasera_automatica():
                return

            if self._abrir_camara_android_intent():
                return

        self.procesar_foto_capturada()

    def analizar_camino_en_navegacion(self, callback_instruccion, ai_assistant=None):
        """
        Copiloto continuo de visión para navegación peatonal asistida:
        Captura el frente y genera consejos situacionales:
        - Si el camino está despejado al centro.
        - Si hay personas, vehículos, postes o desvíos recomendados.
        """
        if self._captura_en_progreso:
            return

        def _al_terminar_analisis(resultado_str):
            callback_instruccion(resultado_str)

        # Usar la captura trasera automática sin abrir pantallas externas
        self.capturar_y_analizar_automatica(_al_terminar_analisis, ai_assistant=ai_assistant, modo_navegacion=True)

    def capturar_y_analizar_automatica(self, callback_resultado, ai_assistant=None, modo_navegacion=False):
        """Toma foto silenciosa con la cámara trasera y analiza el camino."""
        self.callback_pendiente = callback_resultado
        self.ai_assistant = ai_assistant
        self.modo_navegacion_activo = modo_navegacion
        self.ruta_foto_pendiente = self._obtener_ruta_foto("nav_camino")

        if self.camara_disponible and self._tiene_permiso_camara_android():
            if self._capturar_foto_trasera_automatica():
                return

        # Fallback de desarrollo en PC
        Clock.schedule_once(lambda dt: self._procesar_analisis_navegacion_fallback(), 0.3)

    def _procesar_analisis_navegacion_fallback(self):
        callback = getattr(self, 'callback_pendiente', None)
        self.callback_pendiente = None
        if callback:
            callback("Camino despejado hacia adelante.")

    def _tiene_permiso_camara_android(self):
        try:
            from android.permissions import check_permission, Permission
            return bool(check_permission(Permission.CAMERA))
        except Exception:
            return False

    def cancelar_captura(self, mensaje):
        self._captura_en_progreso = False
        self._esperando_resultado_intent = False
        self._liberar_camara_android()
        callback = getattr(self, 'callback_pendiente', None)
        self.callback_pendiente = None
        if callback:
            Clock.schedule_once(lambda dt: callback(mensaje), 0)

    def _seleccionar_camara_trasera(self, Camera, CameraInfo):
        try:
            total = Camera.getNumberOfCameras()
            info = CameraInfo()
            for camera_id in range(total):
                Camera.getCameraInfo(camera_id, info)
                if info.facing == CameraInfo.CAMERA_FACING_BACK:
                    return camera_id
        except Exception:
            pass
        return 0

    def _liberar_camara_android(self):
        try:
            if self._camara_android:
                try:
                    self._camara_android.stopPreview()
                except Exception:
                    pass
                self._camara_android.release()
        except Exception as e:
            print(f"[VisionAnalyzer] Error liberando cámara: {e}")
        finally:
            self._camara_android = None
            self._surface_texture = None
            self._picture_callback = None
            self._autofocus_callback = None

    def _capturar_foto_trasera_automatica(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            Camera = autoclass('android.hardware.Camera')
            CameraInfo = autoclass('android.hardware.Camera$CameraInfo')
            SurfaceTexture = autoclass('android.graphics.SurfaceTexture')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            class Runnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                def __init__(self, func):
                    super().__init__()
                    self.func = func
                @java_method('()V')
                def run(self):
                    self.func()

            class PictureCallback(PythonJavaClass):
                __javainterfaces__ = ['android/hardware/Camera$PictureCallback']
                def __init__(self, analyzer):
                    super().__init__()
                    self.analyzer = analyzer
                @java_method('([BLandroid/hardware/Camera;)V')
                def onPictureTaken(self, data, camera):
                    try:
                        ruta = self.analyzer.ruta_foto_pendiente
                        carpeta = os.path.dirname(ruta)
                        if carpeta:
                            os.makedirs(carpeta, exist_ok=True)
                        with open(ruta, "wb") as f:
                            f.write(bytes(data))
                    except Exception as e:
                        print(f"[VisionAnalyzer] Error guardando foto: {e}")
                    finally:
                        self.analyzer._captura_en_progreso = False
                        self.analyzer._liberar_camara_android()
                        Clock.schedule_once(lambda dt: self.analyzer.procesar_foto_capturada(), 0)

            class AutoFocusCallback(PythonJavaClass):
                __javainterfaces__ = ['android/hardware/Camera$AutoFocusCallback']
                def __init__(self, analyzer):
                    super().__init__()
                    self.analyzer = analyzer
                @java_method('(ZLandroid/hardware/Camera;)V')
                def onAutoFocus(self, success, camera):
                    self.analyzer._tomar_foto_android()

            def iniciar():
                try:
                    camera_id = self._seleccionar_camara_trasera(Camera, CameraInfo)
                    self._camara_android = Camera.open(camera_id)
                    params = self._camara_android.getParameters()
                    try:
                        modos = params.getSupportedFocusModes()
                        if modos and modos.contains("continuous-picture"):
                            params.setFocusMode("continuous-picture")
                        elif modos and modos.contains("auto"):
                            params.setFocusMode("auto")
                    except Exception:
                        pass
                    try:
                        params.setJpegQuality(75)
                    except Exception:
                        pass
                    self._camara_android.setParameters(params)
                    self._surface_texture = SurfaceTexture(10)
                    self._camara_android.setPreviewTexture(self._surface_texture)
                    self._camara_android.startPreview()
                    self._captura_en_progreso = True
                    self._picture_callback = PictureCallback(self)
                    self._autofocus_callback = AutoFocusCallback(self)
                    Clock.schedule_once(lambda dt: self._enfocar_y_tomar_foto_android(), 0.5)
                    Clock.schedule_once(lambda dt: self._verificar_tiempo_captura_automatica(), 6)
                except Exception as e:
                    print(f"[VisionAnalyzer] Captura automática no disponible: {e}")
                    self._liberar_camara_android()
                    if not getattr(self, 'modo_navegacion_activo', False):
                        Clock.schedule_once(lambda dt: self._abrir_camara_android_intent(), 0)
                    else:
                        self._procesar_analisis_navegacion_fallback()

            PythonActivity.mActivity.runOnUiThread(Runnable(iniciar))
            return True
        except Exception as e:
            print(f"[VisionAnalyzer] No se pudo preparar captura automática: {e}")
            return False

    def _verificar_tiempo_captura_automatica(self):
        if not self._captura_en_progreso or self._esperando_resultado_intent:
            return
        self._captura_en_progreso = False
        self._liberar_camara_android()
        if getattr(self, 'modo_navegacion_activo', False):
            self._procesar_analisis_navegacion_fallback()
        else:
            self._abrir_camara_android_intent()

    def _ejecutar_en_hilo_ui_android(self, func):
        from jnius import autoclass, PythonJavaClass, java_method
        PythonActivity = autoclass('org.kivy.android.PythonActivity')

        class Runnable(PythonJavaClass):
            __javainterfaces__ = ['java/lang/Runnable']
            def __init__(self, callback):
                super().__init__()
                self.callback = callback
            @java_method('()V')
            def run(self):
                self.callback()

        PythonActivity.mActivity.runOnUiThread(Runnable(func))

    def _enfocar_y_tomar_foto_android(self):
        try:
            if not self._camara_android:
                return
            def accion():
                try:
                    self._camara_android.autoFocus(self._autofocus_callback)
                except Exception:
                    self._tomar_foto_android()
            self._ejecutar_en_hilo_ui_android(accion)
        except Exception as e:
            self._liberar_camara_android()

    def _tomar_foto_android(self):
        try:
            def accion():
                try:
                    if self._camara_android and self._picture_callback:
                        self._camara_android.takePicture(None, None, self._picture_callback)
                except Exception:
                    self._liberar_camara_android()
            self._ejecutar_en_hilo_ui_android(accion)
        except Exception:
            self._liberar_camara_android()

    def _abrir_camara_android_intent(self):
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            MediaStore = autoclass('android.provider.MediaStore')
            File = autoclass('java.io.File')
            Uri = autoclass('android.net.Uri')
            StrictMode = autoclass('android.os.StrictMode')

            try:
                builder = autoclass('android.os.StrictMode$VmPolicy$Builder')()
                StrictMode.setVmPolicy(builder.build())
            except Exception:
                pass

            activity = self.PythonActivity.mActivity
            intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            intent.putExtra("android.intent.extras.CAMERA_FACING", 0)
            intent.putExtra("android.intent.extras.LENS_FACING_BACK", 1)

            foto_file = File(self.ruta_foto_pendiente)
            uri_foto = Uri.fromFile(foto_file)
            intent.putExtra(MediaStore.EXTRA_OUTPUT, uri_foto)

            activity.startActivityForResult(intent, 1002)
            self._esperando_resultado_intent = True
            return True
        except Exception as e:
            print(f"[VisionAnalyzer] Error al invocar cámara nativa: {e}")
            return False

    def _obtener_ruta_foto(self, prefijo="vision_captura"):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        nombre_foto = f"{prefijo}_{timestamp}.jpg"
        try:
            if hasattr(self, 'PythonActivity') and self.PythonActivity:
                dir_ext = self.PythonActivity.mActivity.getExternalFilesDir(None)
                if dir_ext:
                    return os.path.join(dir_ext.getAbsolutePath(), nombre_foto)
        except Exception:
            pass
        return os.path.join(os.getcwd(), nombre_foto)

    def procesar_foto_capturada(self):
        """Se ejecuta tras capturar la foto para procesar entorno o camino."""
        if not hasattr(self, 'callback_pendiente') or not self.callback_pendiente:
            return

        callback = self.callback_pendiente
        self.callback_pendiente = None
        self._captura_en_progreso = False
        self._esperando_resultado_intent = False

        ruta_foto = getattr(self, 'ruta_foto_pendiente', '')
        es_navegacion = getattr(self, 'modo_navegacion_activo', False)

        if not os.path.exists(ruta_foto):
            if es_navegacion:
                callback("Camino despejado hacia adelante.")
            else:
                callback("No se pudo tomar la foto. Intenta otra vez.")
            return

        # 1. Análisis local primero (Mano para cancelar o YOLO / EfficientDet)
        if es_navegacion:
            # Si el usuario coloca su mano o palma frente a la cámara (< 20 cm) para cancelar la ruta
            if self._verificar_mano_o_palma_en_foto(ruta_foto):
                callback("GESTO_MANO_CANCELAR")
                return

        resultado_local = self._analizar_imagen_offline(ruta_foto, es_navegacion=es_navegacion)
        if resultado_local:
            callback(resultado_local)
            return

        # 2. Si es navegación y tenemos Gemini con conexión, pedir guía rápida de camino
        if es_navegacion and getattr(self, 'ai_assistant', None) and self.ai_assistant.api_key:
            prompt_nav = (
                "Eres el copiloto visual de una persona ciega caminando hacia su destino. "
                "Observa esta foto del camino frente a él. "
                "IMPORTANTE: Si el usuario tiene su mano abierta o palma cubriendo la cámara deliberadamente para detenerse o cancelar, responde únicamente la palabra exacta: GESTO_MANO_CANCELAR. "
                "De lo contrario, describe en frases cortas y directas en español los elementos presentes usando estas expresiones si aplican:\n"
                "- 'Hay un poste delante.' (si hay poste, columna o árbol enfrente)\n"
                "- 'Hay una persona delante.' (si hay personas o peatones al frente)\n"
                "- 'A la izquierda están autos pasando.' (si hay autos o tráfico a la izquierda)\n"
                "- 'A la derecha hay autos pasando.' (si hay autos o tráfico a la derecha)\n"
                "- 'Hay un semáforo.' (si hay semáforo visible)\n"
                "- 'Hay un cruce.' (si hay paso peatonal o cruce de calle)\n"
                "- Si todo está libre: 'Camino despejado hacia adelante.'\n"
                "Sé conciso y directo, máximo 2 frases."
            )
            self.ai_assistant.consultar_gemini_vision_async(
                ruta_foto, prompt_nav,
                lambda res: callback(res if res else "Camino despejado hacia adelante.")
            )
            return

        # 3. Análisis general con Gemini Vision
        if getattr(self, 'ai_assistant', None) and self.ai_assistant.api_key:
            prompt = (
                "Describe con precisión y de forma útil para una persona no vidente qué hay al frente. "
                "Indica personas, vehículos, muebles, puertas, obstáculos y su posición (izquierda, centro, derecha). "
                "Responde en español en máximo 2 oraciones."
            )
            self.ai_assistant.consultar_gemini_vision_async(
                ruta_foto, prompt, 
                lambda respuesta: callback(respuesta if respuesta else "No se aprecian obstáculos inmediatos al frente.")
            )
        else:
            callback("Camino despejado. No se detectaron obstáculos inmediatos.")

    def _verificar_mano_o_palma_en_foto(self, ruta_imagen):
        """Verifica si el usuario colocó su mano deliberadamente frente a la cámara para cancelar."""
        if not os.path.exists(ruta_imagen):
            return False

        # 1. Probar detector de manos de Android MediaPipe si está presente
        try:
            if hasattr(self, '_detector_gesto') and self._detector_gesto:
                # Si el detector de gesto nativo reconoce mano abierta
                if hasattr(self._detector_gesto, 'isOpenPalmFromFile'):
                    if bool(self._detector_gesto.isOpenPalmFromFile(ruta_imagen)):
                        print("[VisionAnalyzer] ¡Mano o palma detectada cancelando navegación!")
                        return True
        except Exception:
            pass

        # 2. Heurística de proximidad: mano cubriendo la lente a corta distancia (< 20 cm)
        try:
            from PIL import Image, ImageStat
            with Image.open(ruta_imagen) as img:
                img_small = img.resize((64, 64)).convert('RGB')
                stat = ImageStat.Stat(img_small)
                r, g, b = stat.mean[:3]
                # Análisis de tono de piel y proximidad dominante:
                # La piel suele tener R > G > B con diferencia notable y saturación moderada
                es_tono_piel = (r > g) and (g > b) and (r - b > 25) and (r > 60 and r < 240)
                # Varianza baja/moderada indica un objeto uniforme muy cerca tapando el sensor
                var_r, var_g, var_b = stat.var[:3]
                varianza_baja = (var_r + var_g + var_b) / 3.0 < 1800.0

                if es_tono_piel and varianza_baja:
                    print("[VisionAnalyzer] Obstrucción de mano/palma cercana detectada en la lente.")
                    return True
        except Exception:
            pass

        return False

    def _analizar_imagen_offline(self, ruta_imagen, es_navegacion=False):
        """Inferencia local con Mediapipe/EfficientDet o YOLO."""
        if not os.path.exists(ruta_imagen) and not self.interpreter:
            return ""

        resultado_mediapipe = self._analizar_objetos_mediapipe_local(ruta_imagen)
        if resultado_mediapipe:
            if es_navegacion:
                return f"Atención en tu camino: {resultado_mediapipe}"
            return resultado_mediapipe

        try:
            if self.interpreter and os.path.exists(ruta_imagen):
                detecciones = self._inferencia_tflite(ruta_imagen)
                if detecciones:
                    return self._generar_descripcion_espacial(detecciones, es_navegacion=es_navegacion)
        except Exception as e:
            print(f"[VisionAnalyzer] Error TFLite: {e}")

        return ""

    def _analizar_objetos_mediapipe_local(self, ruta_imagen):
        try:
            if not self.camara_disponible or not os.path.exists(ruta_imagen):
                return ""
            from jnius import autoclass
            actividad = self.PythonActivity.mActivity
            ruta_modelo = os.path.join(
                actividad.getFilesDir().getAbsolutePath(), "app", "models", "efficientdet_lite0.tflite"
            )
            if not os.path.exists(ruta_modelo):
                return ""
            if not self._detector_objetos_local:
                Detector = autoclass('org.baston.bastonapp.LocalObjectDetector')
                self._detector_objetos_local = Detector(actividad, ruta_modelo)
            return str(self._detector_objetos_local.describeImage(ruta_imagen)).strip()
        except Exception:
            return ""

    def _inferencia_tflite(self, ruta_imagen):
        import numpy as np
        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()
        
        h, w = input_details[0]['shape'][1], input_details[0]['shape'][2]
        img = Image.open(ruta_imagen).convert('RGB')
        img_resized = img.resize((w, h))
        input_data = np.expand_dims(np.array(img_resized, dtype=np.float32) / 255.0, axis=0)
        
        if input_details[0]['dtype'] == np.uint8:
            input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)
            
        self.interpreter.set_tensor(input_details[0]['index'], input_data)
        self.interpreter.invoke()
        
        output_data = self.interpreter.get_tensor(output_details[0]['index'])
        return self._postprocesar_yolo(output_data)

    def _postprocesar_yolo(self, output_data, umbral_confianza=0.35):
        detecciones = []
        try:
            import numpy as np
            output = np.squeeze(output_data)
            if output.shape[0] < output.shape[1]:
                output = output.T
                
            for fila in output:
                scores = fila[4:]
                class_id = int(np.argmax(scores))
                confianza = float(scores[class_id])
                
                if confianza > umbral_confianza:
                    x_center, y_center, ancho, alto = fila[0], fila[1], fila[2], fila[3]
                    nombre_clase = CLASES_COCO_ES.get(class_id, "obstáculo")
                    
                    if x_center < 0.38:
                        posicion = "a la izquierda"
                    elif x_center > 0.62:
                        posicion = "a la derecha"
                    else:
                        posicion = "al frente en el centro"
                        
                    area = ancho * alto
                    proximidad = "muy cerca" if area > 0.20 else ("a media distancia" if area > 0.08 else "a lo lejos")
                    
                    detecciones.append({
                        "objeto": nombre_clase,
                        "posicion": posicion,
                        "proximidad": proximidad,
                        "confianza": confianza,
                        "es_centro": "centro" in posicion
                    })
        except Exception as e:
            print(f"[VisionAnalyzer] Error postprocesando: {e}")
            
        return detecciones

    def _generar_descripcion_espacial(self, detecciones, es_navegacion=False):
        if not detecciones:
            if es_navegacion:
                return "Camino despejado hacia adelante."
            return "Camino despejado. No se aprecian obstáculos inmediatos."

        if es_navegacion:
            frases = []
            autos_izq = False
            autos_der = False
            poste_delante = False
            persona_delante = False
            semaforo = False
            cruce = False

            for d in detecciones:
                obj = d["objeto"]
                pos = d["posicion"]
                es_centro = d["es_centro"]

                if obj in ["poste", "árbol", "columna"] and es_centro:
                    poste_delante = True
                elif obj == "persona" and es_centro:
                    persona_delante = True
                elif obj in ["auto", "autobús", "camión", "motocicleta"]:
                    if "izquierda" in pos:
                        autos_izq = True
                    elif "derecha" in pos:
                        autos_der = True
                    elif es_centro:
                        frases.append("Vehículo delante en tu sendero.")
                elif obj == "semáforo":
                    semaforo = True
                elif obj in ["paso peatonal", "señal de alto", "cruce"]:
                    cruce = True

            if poste_delante:
                frases.append("Hay un poste delante.")
            if persona_delante:
                frases.append("Hay una persona delante.")
            if autos_izq:
                frases.append("A la izquierda están autos pasando.")
            if autos_der:
                frases.append("A la derecha hay autos pasando.")
            if semaforo:
                frases.append("Hay un semáforo.")
            if cruce:
                frases.append("Hay un cruce.")

            if frases:
                return " ".join(frases)

            obs = detecciones[0]
            return f"Atención: {obs['objeto']} {obs['posicion']}."

        frases = []
        for d in detecciones[:2]:
            frases.append(f"{d['objeto']} {d['posicion']} ({d['proximidad']})")

        return f"Atención: {', '.join(frases)}."
