import os
import time
import glob

class DocumentReader:
    def __init__(self):
        self.camara_disponible = False
        self.callback_pendiente = None
        self.ai_assistant = None
        self.ruta_foto_pendiente = ""
        self._tiempo_inicio_captura = 0.0
        self._captura_en_progreso = False
        self._esperando_resultado_intent = False
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
        self._tiempo_inicio_captura = time.time()
        self._captura_en_progreso = True

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
                intent.putExtra("android.intent.extras.CAMERA_FACING", 0)
                intent.putExtra("android.intent.extras.LENS_FACING_BACK", 1)

                foto_file = File(self.ruta_foto_pendiente)
                uri_foto = Uri.fromFile(foto_file)
                intent.putExtra(MediaStore.EXTRA_OUTPUT, uri_foto)

                self._esperando_resultado_intent = True
                activity.startActivityForResult(intent, 1003)
                return
            except Exception as e:
                print(f"[DocumentReader] Error al invocar cámara nativa: {e}")

        self.procesar_foto_capturada()

    def _obtener_ruta_foto(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        nombre_foto = f"doc_captura_{timestamp}.jpg"

        # 1. Directorio de archivos externos de la app (preferido en Android)
        try:
            if hasattr(self, 'PythonActivity') and self.PythonActivity:
                dir_ext = self.PythonActivity.mActivity.getExternalFilesDir(None)
                if dir_ext:
                    ruta = os.path.join(dir_ext.getAbsolutePath(), nombre_foto)
                    os.makedirs(os.path.dirname(ruta), exist_ok=True)
                    return ruta
        except Exception:
            pass

        # 2. Directorio de caché
        try:
            if hasattr(self, 'PythonActivity') and self.PythonActivity:
                dir_cache = self.PythonActivity.mActivity.getCacheDir()
                if dir_cache:
                    return os.path.join(dir_cache.getAbsolutePath(), nombre_foto)
        except Exception:
            pass

        # 3. Directorios compartidos estándar
        for posible_dir in ["/sdcard/DCIM/Camera", "/sdcard/Pictures", "/storage/emulated/0/DCIM/Camera", "/storage/emulated/0/Pictures"]:
            if os.path.exists(posible_dir):
                return os.path.join(posible_dir, nombre_foto)

        return os.path.join(os.getcwd(), nombre_foto)

    def cancelar_captura(self, mensaje):
        self._captura_en_progreso = False
        self._esperando_resultado_intent = False
        callback = self.callback_pendiente
        self.callback_pendiente = None
        if callback:
            callback(mensaje)

    def procesar_foto_capturada(self, intent_data=None):
        if not self.callback_pendiente:
            return

        callback = self.callback_pendiente
        self.callback_pendiente = None
        self._captura_en_progreso = False
        self._esperando_resultado_intent = False

        ruta_foto = self._resolver_archivo_foto(intent_data)

        # Si tenemos un asistente con clave API y la foto existe
        if self.ai_assistant and hasattr(self.ai_assistant, 'consultar_gemini_documento_async') and ruta_foto and os.path.exists(ruta_foto):
            def _al_recibir_lectura(respuesta):
                if respuesta:
                    resp_limpia = respuesta.strip()
                    if any(resp_limpia.startswith(pref) for pref in ["No se ", "Para leer ", "Ocurrió ", "Error "]):
                        callback(resp_limpia)
                    else:
                        callback(f"Documento leído:\n{resp_limpia}")
                else:
                    callback(self._procesar_ocr_local(ruta_foto))
                self._limpiar_fotos_antiguas()

            self.ai_assistant.consultar_gemini_documento_async(ruta_foto, _al_recibir_lectura)
        elif self.ai_assistant and hasattr(self.ai_assistant, 'consultar_gemini_vision_async') and self.ai_assistant.api_key and ruta_foto and os.path.exists(ruta_foto):
            prompt = "Lee y transcribe con precisión en español todo el texto, título, valores o instrucciones de este documento, pantalla o etiqueta."
            def _al_recibir_vision(respuesta):
                if respuesta:
                    resp_limpia = respuesta.strip()
                    if any(resp_limpia.startswith(pref) for pref in ["No se ", "Para leer ", "Ocurrió ", "Error "]):
                        callback(resp_limpia)
                    else:
                        callback(f"Documento leído:\n{resp_limpia}")
                else:
                    callback(self._procesar_ocr_local(ruta_foto))
                self._limpiar_fotos_antiguas()

            self.ai_assistant.consultar_gemini_vision_async(ruta_foto, prompt, _al_recibir_vision)
        else:
            callback(self._procesar_ocr_local(ruta_foto))

    def _resolver_archivo_foto(self, intent_data=None):
        """Recupera la imagen tomada ya sea del archivo directo, del intent_data o de la galería reciente."""
        # 1. Comprobar si la ruta directa se guardó correctamente
        if self.ruta_foto_pendiente and os.path.exists(self.ruta_foto_pendiente):
            try:
                if os.path.getsize(self.ruta_foto_pendiente) > 200:
                    return self.ruta_foto_pendiente
            except Exception:
                pass

        # 2. Comprobar si la foto vino en intent_data (URI o Bitmap)
        if intent_data and hasattr(self, 'PythonActivity') and self.PythonActivity:
            try:
                uri = intent_data.getData()
                if uri:
                    cr = self.PythonActivity.mActivity.getContentResolver()
                    in_stream = cr.openInputStream(uri)
                    if in_stream:
                        ruta_destino = self.ruta_foto_pendiente or self._obtener_ruta_foto()
                        with open(ruta_destino, "wb") as out_f:
                            buf = bytearray(8192)
                            while True:
                                read = in_stream.read(buf)
                                if read <= 0:
                                    break
                                out_f.write(buf[:read])
                        in_stream.close()
                        if os.path.exists(ruta_destino) and os.path.getsize(ruta_destino) > 200:
                            return ruta_destino
            except Exception as e:
                print(f"[DocumentReader] Error al recuperar foto desde URI: {e}")

            # Intentar extraer Bitmap de extras
            try:
                extras = intent_data.getExtras()
                if extras and extras.containsKey("data"):
                    bitmap = extras.get("data")
                    if bitmap:
                        from jnius import autoclass
                        CompressFormat = autoclass('android.graphics.Bitmap$CompressFormat')
                        FileOutputStream = autoclass('java.io.FileOutputStream')
                        ruta_destino = self.ruta_foto_pendiente or self._obtener_ruta_foto()
                        fos = FileOutputStream(ruta_destino)
                        bitmap.compress(CompressFormat.JPEG, 90, fos)
                        fos.flush()
                        fos.close()
                        if os.path.exists(ruta_destino) and os.path.getsize(ruta_destino) > 200:
                            return ruta_destino
            except Exception as e:
                print(f"[DocumentReader] Error al recuperar bitmap de extras: {e}")

        # 3. Buscar la foto más reciente en carpetas de cámara de Android modificada hace menos de 120 segundos
        directorios_camara = [
            "/sdcard/DCIM/Camera",
            "/storage/emulated/0/DCIM/Camera",
            "/sdcard/DCIM",
            "/storage/emulated/0/DCIM",
            "/sdcard/DCIM/100ANDRO",
            "/storage/emulated/0/DCIM/100ANDRO",
            "/sdcard/Pictures",
            "/storage/emulated/0/Pictures"
        ]
        ahora = time.time()
        for d in directorios_camara:
            if os.path.isdir(d):
                try:
                    archivos = []
                    for patron_ext in ["*.[jJ][pP][gG]", "*.[jJ][pP][eE][gG]", "*.[pP][nN][gG]"]:
                        archivos.extend(glob.glob(os.path.join(d, patron_ext)))
                    if archivos:
                        mas_reciente = max(archivos, key=os.path.getmtime)
                        mtime = os.path.getmtime(mas_reciente)
                        if ahora - mtime < 120 and os.path.getsize(mas_reciente) > 500:
                            print(f"[DocumentReader] Foto recuperada desde galería: {mas_reciente}")
                            return mas_reciente
                except Exception:
                    pass

        return self.ruta_foto_pendiente

    def _procesar_ocr_local(self, ruta_imagen):
        if ruta_imagen and os.path.exists(ruta_imagen):
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(ruta_imagen)
                texto = pytesseract.image_to_string(img, lang='spa').strip()
                if texto and len(texto) > 3:
                    return f"Documento leído:\n{texto}"
            except Exception:
                pass

        if self.ai_assistant and not self.ai_assistant.tiene_api_key_configurada():
            return "No se pudo leer el documento. Para leer textos o pantallas, abre 'Configurar Clave API' en la parte superior y pega tu clave de Google AI Studio."

        return "No se pudo detectar texto legible en el documento. Asegúrate de enfocar con nitidez la pantalla o papel con la cámara."

    def _limpiar_fotos_antiguas(self):
        """Elimina capturas temporales de documentos anteriores para no saturar almacenamiento."""
        try:
            directorio = os.path.dirname(self.ruta_foto_pendiente)
            if directorio and os.path.isdir(directorio):
                ahora = time.time()
                for nombre in os.listdir(directorio):
                    if nombre.startswith("doc_captura_") and nombre.endswith(".jpg"):
                        ruta = os.path.join(directorio, nombre)
                        if ahora - os.path.getmtime(ruta) > 600:
                            try:
                                os.remove(ruta)
                            except Exception:
                                pass
        except Exception:
            pass
