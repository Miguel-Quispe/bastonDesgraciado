import os
import time
from PIL import Image
from kivy.clock import Clock

# Diccionario de traducción de clases COCO (YOLO) a español natural para personas con discapacidad visual
CLASES_COCO_ES = {
    0: "persona", 1: "bicicleta", 2: "auto", 3: "motocicleta", 4: "avión", 5: "autobús",
    6: "tren", 7: "camión", 8: "bote", 9: "semáforo", 10: "hidrante", 11: "señal de alto",
    12: "parquímetro", 13: "banco", 14: "pájaro", 15: "gato", 16: "perro", 17: "caballo",
    18: "oveja", 19: "vaca", 24: "mochila", 25: "paraguas", 26: "bolso", 28: "maleta",
    39: "botella", 41: "taza", 56: "silla", 57: "sofá", 58: "planta", 59: "cama",
    60: "mesa", 62: "televisor", 63: "computadora", 67: "celular", 73: "libro",
    # Clases personalizadas de bastón inteligente (conos, pozos, escalones)
    80: "cono de obra", 81: "escalón", 82: "bache", 83: "paso peatonal"
}

class VisionAnalyzer:
    def __init__(self, ruta_modelo="model/yolov8n.tflite"):
        self.camara_disponible = False
        self.interpreter = None
        self._camara_android = None
        self._surface_texture = None
        self._picture_callback = None
        self._autofocus_callback = None
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
            # Buscar en la raíz si no está en la subcarpeta
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
                print(f"[VisionAnalyzer] Modelo YOLO TFLite ({self.ruta_modelo}) cargado exitosamente. Inferencia offline lista.")
            except Exception as e:
                print(f"[VisionAnalyzer] Error al inicializar TFLite: {e}. Usando procesamiento heurístico.")
        else:
            print(f"[VisionAnalyzer] Aviso: Modelo '{self.ruta_modelo}' no encontrado. Se usará análisis de respaldo.")

    def capturar_y_analizar(self, callback_resultado, ai_assistant=None):
        """Captura una fotografía del entorno y analiza obstáculos y objetos presentes."""
        print("[VisionAnalyzer] Iniciando captura de cámara para análisis de entorno...")
        self.callback_pendiente = callback_resultado
        self.ai_assistant = ai_assistant

        self.ruta_foto_pendiente = self._obtener_ruta_foto()

        if self.camara_disponible:
            if self._capturar_foto_trasera_automatica():
                print(f"[VisionAnalyzer] Captura automática con cámara trasera iniciada: {self.ruta_foto_pendiente}")
                return

            if self._abrir_camara_android_intent():
                return

        # Fallback para entorno de desarrollo PC
        self.procesar_foto_capturada()

    def _seleccionar_camara_trasera(self, Camera, CameraInfo):
        """Devuelve el id de la cámara trasera; si falla, usa la cámara 0."""
        try:
            total = Camera.getNumberOfCameras()
            info = CameraInfo()
            for camera_id in range(total):
                Camera.getCameraInfo(camera_id, info)
                if info.facing == CameraInfo.CAMERA_FACING_BACK:
                    return camera_id
        except Exception as e:
            print(f"[VisionAnalyzer] No se pudo seleccionar cámara trasera: {e}")
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
        """Toma una foto sin interacción usando la cámara trasera nativa de Android."""
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
                        print(f"[VisionAnalyzer] Foto trasera automática guardada: {ruta}")
                    except Exception as e:
                        print(f"[VisionAnalyzer] Error guardando foto automática: {e}")
                    finally:
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
                        params.setJpegQuality(85)
                    except Exception:
                        pass
                    self._camara_android.setParameters(params)
                    self._surface_texture = SurfaceTexture(10)
                    self._camara_android.setPreviewTexture(self._surface_texture)
                    self._camara_android.startPreview()
                    self._picture_callback = PictureCallback(self)
                    self._autofocus_callback = AutoFocusCallback(self)
                    Clock.schedule_once(lambda dt: self._enfocar_y_tomar_foto_android(), 0.9)
                except Exception as e:
                    print(f"[VisionAnalyzer] Captura automática trasera no disponible: {e}")
                    self._liberar_camara_android()
                    Clock.schedule_once(lambda dt: self._abrir_camara_android_intent(), 0)

            PythonActivity.mActivity.runOnUiThread(Runnable(iniciar))
            return True
        except Exception as e:
            print(f"[VisionAnalyzer] No se pudo preparar captura automática: {e}")
            return False

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
            print(f"[VisionAnalyzer] Error enfocando cámara: {e}")
            self._liberar_camara_android()
            self._abrir_camara_android_intent()

    def _tomar_foto_android(self):
        try:
            def accion():
                try:
                    if self._camara_android and self._picture_callback:
                        self._camara_android.takePicture(None, None, self._picture_callback)
                except Exception as e:
                    print(f"[VisionAnalyzer] Error tomando foto automática: {e}")
                    self._liberar_camara_android()
                    self._abrir_camara_android_intent()

            self._ejecutar_en_hilo_ui_android(accion)
        except Exception as e:
            print(f"[VisionAnalyzer] Error tomando foto automática: {e}")
            self._liberar_camara_android()
            self._abrir_camara_android_intent()

    def _abrir_camara_android_intent(self):
        """Respaldo: abre la app de cámara pidiendo cámara trasera si es posible."""
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
            intent.putExtra("android.intent.extra.USE_FRONT_CAMERA", False)

            foto_file = File(self.ruta_foto_pendiente)
            uri_foto = Uri.fromFile(foto_file)
            intent.putExtra(MediaStore.EXTRA_OUTPUT, uri_foto)

            activity.startActivityForResult(intent, 1002)
            print(f"[VisionAnalyzer] Intent de cámara trasera lanzado. Guardando en: {self.ruta_foto_pendiente}")
            return True
        except Exception as e:
            print(f"[VisionAnalyzer] Error al invocar cámara nativa: {e}")
            return False

    def _obtener_ruta_foto(self):
        """Genera una ruta persistente para guardar la foto capturada."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        nombre_foto = f"vision_captura_{timestamp}.jpg"
        try:
            if hasattr(self, 'PythonActivity') and self.PythonActivity:
                dir_ext = self.PythonActivity.mActivity.getExternalFilesDir(None)
                if dir_ext:
                    return os.path.join(dir_ext.getAbsolutePath(), nombre_foto)
        except Exception as e:
            print(f"[VisionAnalyzer] Error al obtener dir externo: {e}")
        return os.path.join(os.getcwd(), nombre_foto)

    def procesar_foto_capturada(self):
        """Se ejecuta al volver de la cámara de Android con la fotografía tomada."""
        if not hasattr(self, 'callback_pendiente') or not self.callback_pendiente:
            return

        callback = self.callback_pendiente
        self.callback_pendiente = None

        ruta_foto = getattr(self, 'ruta_foto_pendiente', '')

        # Si tenemos IA Gemini activa y foto existente, usamos Gemini Vision para análisis visual completo
        if getattr(self, 'ai_assistant', None) and self.ai_assistant.api_key and os.path.exists(ruta_foto):
            print("[VisionAnalyzer] Enviando fotografía del entorno a Gemini Vision para análisis...")
            prompt = "Describe en 1 o 2 oraciones sencillas en español para una persona no vidente qué objetos, personas u obstáculos hay al frente en el camino."
            self.ai_assistant.consultar_gemini_vision_async(
                ruta_foto, prompt, 
                lambda respuesta: callback(f"Visión: {respuesta}" if respuesta else self._analizar_imagen_offline(ruta_foto))
            )
        else:
            resultado_local = self._analizar_imagen_offline(ruta_foto)
            callback(resultado_local)

    def _analizar_imagen_offline(self, ruta_imagen):
        """Ejecuta inferencia con YOLO TFLite y genera una descripción espacial en español."""
        if not os.path.exists(ruta_imagen) and not self.interpreter:
            return "Visión: No pude capturar una foto del frente. Revisa el permiso de cámara e intenta otra vez."

        try:
            # Si el intérprete TFLite está activo, procesamos la imagen
            if self.interpreter and os.path.exists(ruta_imagen):
                detecciones = self._inferencia_tflite(ruta_imagen)
                if detecciones:
                    return self._generar_descripcion_espacial(detecciones)
        except Exception as e:
            print(f"[VisionAnalyzer] Error en inferencia TFLite: {e}")

        return "Visión: Objeto detectado al frente. Mantén precaución al caminar."

    def _inferencia_tflite(self, ruta_imagen):
        """Preprocesa la imagen y ejecuta el grafo TFLite."""
        import numpy as np
        
        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()
        
        # Dimensiones esperadas por YOLO (ej. 1x640x640x3 o 1x320x320x3)
        input_shape = input_details[0]['shape']
        h, w = input_shape[1], input_shape[2]
        
        img = Image.open(ruta_imagen).convert('RGB')
        img_resized = img.resize((w, h))
        input_data = np.expand_dims(np.array(img_resized, dtype=np.float32) / 255.0, axis=0)
        
        # Si el modelo espera uint8 cuantizado
        if input_details[0]['dtype'] == np.uint8:
            input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)
            
        self.interpreter.set_tensor(input_details[0]['index'], input_data)
        self.interpreter.invoke()
        
        output_data = self.interpreter.get_tensor(output_details[0]['index'])
        return self._postprocesar_yolo(output_data)

    def _postprocesar_yolo(self, output_data, umbral_confianza=0.35):
        """Filtra y extrae coordenadas, etiquetas y posición de las detecciones."""
        detecciones = []
        # YOLOv8 TFLite normalmente devuelve shape [1, 84, 8400] o [1, 8400, 84]
        try:
            import numpy as np
            output = np.squeeze(output_data)
            if output.shape[0] < output.shape[1]:
                output = output.T # Transponer a [8400, 84]
                
            for fila in output:
                scores = fila[4:]
                class_id = int(np.argmax(scores))
                confianza = float(scores[class_id])
                
                if confianza > umbral_confianza:
                    x_center, y_center, ancho, alto = fila[0], fila[1], fila[2], fila[3]
                    nombre_clase = CLASES_COCO_ES.get(class_id, "obstáculo")
                    
                    # Determinar posición horizontal relativa (0.0 a 1.0)
                    if x_center < 0.38:
                        posicion = "a la izquierda"
                    elif x_center > 0.62:
                        posicion = "a la derecha"
                    else:
                        posicion = "al frente en el centro"
                        
                    # Determinar proximidad estimada por el tamaño del objeto
                    area = ancho * alto
                    proximidad = "cerca" if area > 0.15 else "a media distancia"
                    
                    detecciones.append({
                        "objeto": nombre_clase,
                        "posicion": posicion,
                        "proximidad": proximidad,
                        "confianza": confianza
                    })
        except Exception as e:
            print(f"[VisionAnalyzer] Error postprocesando: {e}")
            
        return detecciones

    def _generar_descripcion_espacial(self, detecciones):
        """Convierte las detecciones en una frase de voz concisa y útil para el usuario."""
        if not detecciones:
            return "Camino despejado. No se aprecian obstáculos inmediatos."

        # Ordenar por proximidad/relevancia
        frases = []
        for d in detecciones[:3]: # Máximo 3 objetos para no saturar de información
            frases.append(f"{d['objeto']} {d['posicion']} ({d['proximidad']})")

        return f"Atención: Se detecta {', '.join(frases)}."
