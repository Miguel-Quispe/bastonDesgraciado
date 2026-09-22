import datetime
import json
import os
import re
import unicodedata

class AgendaManager:
    MESES = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }

    def __init__(self, ruta_archivo="agenda_personal.json"):
        self.ruta_archivo = self._obtener_ruta_persistente(ruta_archivo)
        self.eventos = self._cargar_agenda()
        self._eliminar_vencidos()

    def _obtener_ruta_persistente(self, nombre_archivo):
        if os.path.isabs(nombre_archivo):
            return nombre_archivo
        try:
            from jnius import autoclass
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            return os.path.join(activity.getFilesDir().getAbsolutePath(), nombre_archivo)
        except Exception:
            return os.path.join(os.getcwd(), nombre_archivo)

    @staticmethod
    def _sin_acentos(texto):
        normalizado = unicodedata.normalize('NFD', str(texto).lower())
        return ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')

    def _cargar_agenda(self):
        try:
            if os.path.exists(self.ruta_archivo):
                with open(self.ruta_archivo, "r", encoding="utf-8") as archivo:
                    datos = json.load(archivo)
                    return datos if isinstance(datos, list) else []
        except Exception as error:
            print(f"[AgendaManager] Error al cargar agenda: {error}")
        return []

    def _guardar_agenda(self):
        try:
            carpeta = os.path.dirname(self.ruta_archivo)
            if carpeta:
                os.makedirs(carpeta, exist_ok=True)
            with open(self.ruta_archivo, "w", encoding="utf-8") as archivo:
                json.dump(self.eventos, archivo, ensure_ascii=False, indent=2)
        except Exception as error:
            print(f"[AgendaManager] Error al guardar agenda: {error}")

    def _eliminar_vencidos(self):
        hoy = datetime.date.today()
        activos = []
        for evento in self.eventos:
            vence_el = evento.get("vence_el")
            try:
                if vence_el and datetime.date.fromisoformat(vence_el) < hoy:
                    continue
            except ValueError:
                pass
            activos.append(evento)
        if len(activos) != len(self.eventos):
            self.eventos = activos
            self._guardar_agenda()

    def _fecha_hablada(self, fecha):
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"

    def extraer_fecha_limite(self, texto):
        texto_normalizado = self._sin_acentos(texto)
        indice = texto_normalizado.find("hasta")
        if indice < 0:
            return None, texto.strip()

        descripcion = texto[:indice].strip(" ,.-")
        fecha_texto = texto_normalizado[indice + len("hasta"):].strip(" ,.-")
        hoy = datetime.date.today()
        if fecha_texto in ("hoy", "el dia de hoy"):
            return hoy, descripcion
        if fecha_texto in ("manana", "el dia de manana"):
            return hoy + datetime.timedelta(days=1), descripcion

        coincidencia_numerica = re.search(r"(?:el\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", fecha_texto)
        if coincidencia_numerica:
            dia, mes, anio = coincidencia_numerica.groups()
            anio = int(anio) if anio else hoy.year
            if anio < 100:
                anio += 2000
            try:
                fecha = datetime.date(anio, int(mes), int(dia))
                if not coincidencia_numerica.group(3) and fecha < hoy:
                    fecha = datetime.date(anio + 1, int(mes), int(dia))
                return fecha, descripcion
            except ValueError:
                return None, descripcion

        coincidencia_texto = re.search(r"(?:el\s+)?(\d{1,2})\s+de\s+([a-z]+)(?:\s+de\s+(\d{2,4}))?", fecha_texto)
        if coincidencia_texto:
            dia, nombre_mes, anio = coincidencia_texto.groups()
            mes = self.MESES.get(nombre_mes)
            if not mes:
                return None, descripcion
            anio = int(anio) if anio else hoy.year
            if anio < 100:
                anio += 2000
            if anio < hoy.year:
                # Si el reconocimiento de voz interpretó 2007 en vez de 2027 o un año pasado
                if str(anio).endswith("07"):
                    anio = 2027
                else:
                    anio = hoy.year + 1
            try:
                fecha = datetime.date(anio, mes, int(dia))
                if not coincidencia_texto.group(3) and fecha < hoy:
                    fecha = datetime.date(anio + 1, mes, int(dia))
                return fecha, descripcion
            except ValueError:
                return None, descripcion
        return None, descripcion

    def agregar_evento(self, descripcion_evento):
        fecha_limite, descripcion = self.extraer_fecha_limite(descripcion_evento)
        descripcion = descripcion.strip(" ,.-")
        
        # Limpiar palabras iniciales comunes como "guardar", "anotar", "agendar", etc.
        for pref in ["guardar", "guarda", "agendar", "agenda", "anotar", "anota", "recordar", "recuerda", "agregar", "agrega", "que"]:
            if descripcion.lower().startswith(pref + " "):
                descripcion = descripcion[len(pref):].strip(" ,.-")

        if not descripcion:
            return "No entendí qué deseas guardar. Di: guardar tomar medicina hasta el 25 de septiembre."
        if not fecha_limite:
            return "Para guardarlo necesito la fecha límite. Di: hasta el día, mes y año, por ejemplo hasta el 25 de septiembre de 2027."

        creado = datetime.datetime.now()
        nuevo_item = {
            "id": max((item.get("id", 0) for item in self.eventos), default=0) + 1,
            "creado_en": creado.isoformat(timespec="minutes"),
            "vence_el": fecha_limite.isoformat(),
            "descripcion": descripcion,
        }
        self.eventos.append(nuevo_item)
        self._guardar_agenda()
        return (
            f"Guardado: {descripcion}. Se creó el {self._fecha_hablada(creado.date())} "
            f"y estará activo hasta el {self._fecha_hablada(fecha_limite)}."
        )

    def consultar_agenda(self):
        self._eliminar_vencidos()
        if not self.eventos:
            return "Tu agenda está vacía. No tienes eventos ni recordatorios pendientes."

        frases = []
        for numero, item in enumerate(self.eventos, start=1):
            creado = item.get("creado_en") or item.get("fecha")
            vence_el = item.get("vence_el")
            try:
                fecha_creacion = self._fecha_hablada(datetime.datetime.fromisoformat(creado).date())
            except (TypeError, ValueError):
                fecha_creacion = "fecha no disponible"
            try:
                fecha_limite = self._fecha_hablada(datetime.date.fromisoformat(vence_el)) if vence_el else "sin fecha límite"
            except ValueError:
                fecha_limite = "sin fecha límite"
            frases.append(
                f"Número {numero}: {item.get('descripcion', 'sin descripción')}. "
                f"Guardado el {fecha_creacion}, hasta el {fecha_limite}"
            )

        total = len(self.eventos)
        return f"Tienes {total} recordatorio{'s' if total > 1 else ''}: " + ". ".join(frases) + "."

    def borrar_agenda(self):
        self.eventos = []
        self._guardar_agenda()
        return "Se han borrado todos los recordatorios de tu agenda personal."
