import os
import time

class DocumentReader:
    def __init__(self):
        self.camara_disponible = False
        self.callback_pendiente = None
        self.ai_assistant = None
        self.ruta_foto_pendiente = ""
        self._inicializar_camara()

    def _inicializar_camara(self):
        try:
            from jnius import autoclass
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.camara_disponible = True
        except Exception:
            self.camara_disponible = False

    def capturar_y_leer(self, callback_resultado, ai_assistant=None):
        self.callback_pendiente = callback_resultado
        self.ai_assistant = ai_assistant
        self.ruta_foto_pendiente = self._obtener_ruta_foto()

        if self.camara_disponible:
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
                
                foto_file = File(self.ruta_foto_pendiente)
                uri_foto = Uri.fromFile(foto_file)
                intent.putExtra(MediaStore.EXTRA_OUTPUT, uri_foto)

                activity.startActivityForResult(intent, 1003)
                return
            except Exception as e:
                print(f"[DocumentReader] Error al invocar cámara nativa: {e}")

        self.procesar_foto_capturada()

    def _obtener_ruta_foto(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        nombre_foto = f"doc_captura_{timestamp}.jpg"
        try:
            if hasattr(self, 'PythonActivity') and self.PythonActivity:
                dir_ext = self.PythonActivity.mActivity.getExternalFilesDir(None)
                if dir_ext:
                    return os.path.join(dir_ext.getAbsolutePath(), nombre_foto)
        except Exception:
            pass
        return os.path.join(os.getcwd(), nombre_foto)

    def cancelar_captura(self, mensaje):
        callback = self.callback_pendiente
        self.callback_pendiente = None
        if callback:
            callback(mensaje)

    def procesar_foto_capturada(self):
        if not self.callback_pendiente:
            return

        callback = self.callback_pendiente
        self.callback_pendiente = None
        ruta_foto = self.ruta_foto_pendiente

        if self.ai_assistant and self.ai_assistant.api_key and os.path.exists(ruta_foto):
            prompt = "Lee y transcribe con precisión en español todo el texto, título, valores o instrucciones de este documento o etiqueta."
            self.ai_assistant.consultar_gemini_vision_async(
                ruta_foto, prompt, 
                lambda respuesta: callback(f"Documento leído: {respuesta}" if respuesta else self._procesar_ocr_local(ruta_foto))
            )
        else:
            callback(self._procesar_ocr_local(ruta_foto))

    def _procesar_ocr_local(self, ruta_imagen):
        if os.path.exists(ruta_imagen):
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(ruta_imagen)
                texto = pytesseract.image_to_string(img, lang='spa').strip()
                if texto and len(texto) > 3:
                    return f"Documento leído: {texto}"
            except Exception:
                pass

        return "No se pudo detectar texto legible en el documento. Asegúrate de enfocar bien la hoja."
