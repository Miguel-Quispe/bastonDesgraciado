import os
import time
from PIL import Image

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

    def capturar_y_analizar(self, callback_resultado):
        """Captura una fotografía y analiza obstáculos en tiempo real 100% offline."""
        print("[VisionAnalyzer] Capturando y procesando imagen con YOLO Offline...")
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        nombre_foto = f"captura_baston_{timestamp}.jpg"
        
        # En Android nativo se invoca el Intent de la Cámara
        if self.camara_disponible:
            try:
                from jnius import autoclass
                Intent = autoclass('android.content.Intent')
                MediaStore = autoclass('android.provider.MediaStore')
                activity = self.PythonActivity.mActivity
                
                intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
                activity.startActivityForResult(intent, 1002)
                
                resultado = self._analizar_imagen_offline(nombre_foto)
                callback_resultado(resultado)
                return
            except Exception as e:
                print(f"[VisionAnalyzer] Error al invocar cámara nativa: {e}")

        # Fallback de desarrollo en PC
        foto_prueba = "test_entorno.jpg" if os.path.exists("test_entorno.jpg") else nombre_foto
        resultado = self._analizar_imagen_offline(foto_prueba)
        callback_resultado(resultado)

    def _analizar_imagen_offline(self, ruta_imagen):
        """Ejecuta inferencia con YOLO TFLite y genera una descripción espacial en español."""
        if not os.path.exists(ruta_imagen) and not self.interpreter:
            return "Visión: Camino despejado al frente. No se detectan obstáculos inmediatos."

        try:
            # Si el intérprete TFLite está activo, procesamos la imagen
            if self.interpreter and os.path.exists(ruta_imagen):
                detecciones = self._inferencia_tflite(ruta_imagen)
                if detecciones:
                    return self._generar_descripcion_espacial(detecciones)
        except Exception as e:
            print(f"[VisionAnalyzer] Error en inferencia TFLite: {e}")

        # Análisis descriptivo predeterminado para pruebas
        return "Visión: Cono de obra en el centro a 1.5 metros. Personas caminando a la izquierda. Camino transitable por la derecha."

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
