import math
import time
import requests

class LocationService:
    # Punto de respaldo y centro de búsqueda de la aplicación.
    SANTA_CRUZ_LAT = -17.7833
    SANTA_CRUZ_LON = -63.1821
    MAX_EDAD_UBICACION_MS = 10 * 60 * 1000

    def __init__(self, api_key_mapbox="pk.eyJ1IjoiZGVtb3VzZXIiLCJhIjoiY2xleGFtcGxlMDAwMDAwMDAwMDAwMDAwMCJ9.example"):
        self.api_key = api_key_mapbox
        self.navegacion_activa = False
        self.destino_lat = None
        self.destino_lon = None
        self.destino_nombre = None
        self.ultima_distancia = None

    def obtener_coordenadas(self):
        """Obtiene la ubicación GPS nativa del dispositivo (LocationManager) o coordenadas simuladas."""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            activity = PythonActivity.mActivity
            
            location_manager = activity.getSystemService(Context.LOCATION_SERVICE)
            ubicaciones = [
                location_manager.getLastKnownLocation('gps'),
                location_manager.getLastKnownLocation('network'),
            ]
            ubicaciones = [ubicacion for ubicacion in ubicaciones if ubicacion]
            if ubicaciones:
                location = max(ubicaciones, key=lambda ubicacion: ubicacion.getTime())
                edad_ms = int(time.time() * 1000) - int(location.getTime())
                if edad_ms <= self.MAX_EDAD_UBICACION_MS:
                    return location.getLatitude(), location.getLongitude()
                print(f"[LocationService] Ubicación guardada demasiado antigua ({edad_ms} ms).")
            
            print("[LocationService] GPS nativo sin ubicación reciente. Usando Santa Cruz de la Sierra como respaldo.")
            return self.SANTA_CRUZ_LAT, self.SANTA_CRUZ_LON
        except Exception as e:
            print(f"[LocationService] Lectura GPS nativa no disponible ({e}). Usando Santa Cruz de la Sierra como respaldo.")
            return self.SANTA_CRUZ_LAT, self.SANTA_CRUZ_LON

    def consultar_direccion_mapbox(self, lat, lon):
        """Geocodificación inversa llamando al API Geocoding de Mapbox o Nominatim."""
        if not self.api_key or "TU_MAPBOX_KEY" in self.api_key or "example" in self.api_key:
            # Fallback a OpenStreetMap Nominatim gratuito
            try:
                url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=es"
                headers = {"User-Agent": "BastonInteligente/1.0"}
                res = requests.get(url, headers=headers, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("display_name", f"Latitud {lat:.4f}, Longitud {lon:.4f}")
            except Exception:
                pass
            return f"Latitud {lat:.4f}, Longitud {lon:.4f} (Zona Centro)"

        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json?access_token={self.api_key}&language=es"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if "features" in data and len(data["features"]) > 0:
                    return data["features"][0]["place_name"]
            return f"Coordenadas: {lat:.4f}, {lon:.4f}"
        except Exception as e:
            print(f"[LocationService] Error en petición Mapbox: {e}")
            return "Error al conectar con el servicio de mapas"

    def buscar_y_establecer_destino(self, nombre_lugar, lat_actual, lon_actual):
        """Busca un lugar por nombre y lo configura como destino activo."""
        print(f"[LocationService] Buscando destino: {nombre_lugar}...")
        try:
            # Restringir destinos a Bolivia y priorizar Santa Cruz para evitar coincidencias en España.
            consulta = f"{nombre_lugar}, Santa Cruz de la Sierra, Bolivia"
            url = (
                "https://nominatim.openstreetmap.org/search?"
                f"q={requests.utils.quote(consulta)}&format=json&limit=1&accept-language=es"
                "&countrycodes=bo&viewbox=-63.30,-17.70,-63.05,-17.90&bounded=1"
            )
            headers = {"User-Agent": "BastonInteligente/1.0"}
            res = requests.get(url, headers=headers, timeout=6)
            
            if res.status_code == 200:
                data = res.json()
                if data and len(data) > 0:
                    primer_resultado = data[0]
                    lat = float(primer_resultado["lat"])
                    lon = float(primer_resultado["lon"])
                    nombre_display = primer_resultado.get("display_name", nombre_lugar).split(",")[0]
                    
                    return self.establecer_destino_por_coordenadas(lat, lon, nombre_display, lat_actual, lon_actual)
        except Exception as e:
            print(f"[LocationService] Error al buscar lugar: {e}")

        # Fallback de simulación en caso de no encontrar o estar sin internet
        lat_dest = lat_actual + 0.0012
        lon_dest = lon_actual + 0.0008
        return self.establecer_destino_por_coordenadas(lat_dest, lon_dest, nombre_lugar, lat_actual, lon_actual)

    def establecer_destino_por_coordenadas(self, lat, lon, nombre="Destino seleccionado", lat_actual=None, lon_actual=None):
        """Configura un destino a partir de coordenadas enviadas."""
        self.destino_lat = lat
        self.destino_lon = lon
        self.destino_nombre = nombre
        self.navegacion_activa = True
        
        if lat_actual is not None and lon_actual is not None:
            distancia, direccion = self.calcular_distancia_y_rumbo(lat_actual, lon_actual, self.destino_lat, self.destino_lon)
            self.ultima_distancia = distancia
            return f"Ruta iniciada hacia: {self.destino_nombre}. Distancia aproximada: {int(distancia)} metros hacia el {direccion}."
        
        return f"Destino fijado: {self.destino_nombre}."

    def obtener_instruccion_guia(self, lat_actual, lon_actual):
        """Calcula la distancia actual y emite instrucciones de voz según el avance."""
        if not self.navegacion_activa or self.destino_lat is None:
            return None

        distancia, direccion = self.calcular_distancia_y_rumbo(lat_actual, lon_actual, self.destino_lat, self.destino_lon)

        # Si está a menos de 10 metros, ha llegado
        if distancia <= 12:
            nombre = self.destino_nombre
            self.cancelar_navegacion()
            return f"¡Has llegado a tu destino: {nombre}!"

        # Si está a menos de 30 metros
        if distancia <= 30:
            return f"Estás muy cerca de {self.destino_nombre}. A unos {int(distancia)} metros al frente."

        # Instrucción periódica según la distancia
        return f"Continúa hacia el {direccion}. Faltan aproximadamente {int(distancia)} metros para {self.destino_nombre}."

    def cancelar_navegacion(self):
        """Detiene la guía activa."""
        self.navegacion_activa = False
        self.destino_lat = None
        self.destino_lon = None
        self.destino_nombre = None
        self.ultima_distancia = None

    def calcular_distancia_y_rumbo(self, lat1, lon1, lat2, lon2):
        """Calcula la distancia en metros (Fórmula de Haversine) y el rumbo cardinal."""
        R = 6371000 # Radio de la Tierra en metros
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distancia = R * c

        # Cálculo de azimut / rumbo
        y = math.sin(delta_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
        angulo = math.degrees(math.atan2(y, x))
        angulo = (angulo + 360) % 360

        # Mapeo a punto cardinal
        puntos = ["Norte", "Noreste", "Este", "Sureste", "Sur", "Suroeste", "Oeste", "Noroeste"]
        indice = int((angulo + 22.5) / 45) % 8
        rumbo_cardinal = puntos[indice]

        return distancia, rumbo_cardinal
