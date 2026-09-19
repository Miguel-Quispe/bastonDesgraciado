import os
import json
import time

class AgendaManager:
    def __init__(self, ruta_archivo="agenda_personal.json"):
        self.ruta_archivo = ruta_archivo if os.path.isabs(ruta_archivo) else os.path.join(os.getcwd(), ruta_archivo)
        self.eventos = self._cargar_agenda()

    def _cargar_agenda(self):
        """Carga la lista de eventos y notas desde el archivo JSON local."""
        try:
            if os.path.exists(self.ruta_archivo):
                with open(self.ruta_archivo, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[AgendaManager] Error al cargar agenda: {e}")
        return []

    def _guardar_agenda(self):
        """Guarda la lista actualizada de eventos en disco."""
        try:
            with open(self.ruta_archivo, "w", encoding="utf-8") as f:
                json.dump(self.eventos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AgendaManager] Error al guardar agenda: {e}")

    def agregar_evento(self, descripcion_evento):
        """Agrega un nuevo recordatorio o cita a la agenda personal."""
        texto_limpio = descripcion_evento.strip()
        if not texto_limpio:
            return "No entendí el recordatorio. Por favor intenta dictarlo nuevamente."

        timestamp = time.strftime("%Y-%m-%d %H:%M")
        nuevo_item = {
            "id": len(self.eventos) + 1,
            "fecha": timestamp,
            "descripcion": texto_limpio
        }
        self.eventos.append(nuevo_item)
        self._guardar_agenda()
        return f"Recordatorio guardado en la agenda: {texto_limpio}."

    def consultar_agenda(self):
        """Devuelve un resumen hablado de las notas y eventos agendados."""
        if not self.eventos:
            return "Tu agenda está vacía. No tienes eventos ni recordatorios pendientes."

        frases = []
        for i, item in enumerate(self.eventos, start=1):
            frases.append(f"Número {i}: {item['descripcion']}")

        total = len(self.eventos)
        resumen = f"Tienes {total} recordatorio{'s' if total > 1 else ''} en tu agenda: " + ". ".join(frases) + "."
        return resumen

    def borrar_agenda(self):
        """Limpia todos los eventos de la agenda personal."""
        self.eventos = []
        self._guardar_agenda()
        return "Se han borrado todos los recordatorios de tu agenda personal."
