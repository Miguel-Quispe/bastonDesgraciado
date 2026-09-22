import math
import time
import requests

class LocationService:
    # Punto de respaldo en caso de que el GPS no entregue señal reciente
    SANTA_CRUZ_LAT = -17.7833
    SANTA_CRUZ_LON = -63.1821
    MAX_EDAD_UBICACION_MS = 10 * 60 * 1000

    def __init__(self, api_key_mapbox=""):
        self.api_key = api_key_mapbox
        self.navegacion_activa = False
        self.destino_lat = None
        self.destino_lon = None
        self.destino_nombre = None
        self.ultima_distancia = None
        self.ultimo_rumbo = ""

    def obtener_coordenadas(self):
        """Obtiene la ubicación GPS nativa del dispositivo (LocationManager) o coordenadas de respaldo."""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            activity = PythonActivity.mActivity
            
            location_manager = activity.getSystemService(Context.LOCATION_SERVICE)
            ubicaciones = [
                location_manager.getLastKnownLocation('gps'),
                location_manager.getLastKnownLocation('network'),
                location_manager.getLastKnownLocation('passive'),
            ]
            ubicaciones = [ubicacion for ubicacion in ubicaciones if ubicacion]
            if ubicaciones:
                location = max(ubicaciones, key=lambda u: u.getTime())
                edad_ms = int(time.time() * 1000) - int(location.getTime())
                if edad_ms <= self.MAX_EDAD_UBICACION_MS:
                    return location.getLatitude(), location.getLongitude()
                print(f"[LocationService] Ubicación guardada algo antigua ({edad_ms} ms). Usando última conocida.")
                return location.getLatitude(), location.getLongitude()
            
            print("[LocationService] GPS nativo sin ubicación fija. Usando Santa Cruz de la Sierra como respaldo.")
            return self.SANTA_CRUZ_LAT, self.SANTA_CRUZ_LON
        except Exception as e:
            print(f"[LocationService] Lectura GPS nativa no disponible ({e}). Usando respaldo.")
            return self.SANTA_CRUZ_LAT, self.SANTA_CRUZ_LON

    def consultar_direccion_mapbox(self, lat, lon):
        """Geocodificación inversa para saber la calle o dirección actual."""
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=es"
            headers = {"User-Agent": "BastonInteligenteApp/1.0 (accesibilidad visual)"}
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                direccion = data.get("address", {})
                calle = direccion.get("road") or direccion.get("pedestrian") or ""
                barrio = direccion.get("suburb") or direccion.get("neighbourhood") or ""
                ciudad = direccion.get("city") or direccion.get("town") or ""
                
                partes = [p for p in [calle, barrio, ciudad] if p]
                if partes:
                    return ", ".join(partes)
                return data.get("display_name", f"Latitud {lat:.4f}, Longitud {lon:.4f}").split(",")[0]
        except Exception as e:
            print(f"[LocationService] Error geocodificación inversa: {e}")

        return f"Coordenadas: {lat:.4f}, {lon:.4f}"

    def buscar_lugar_cercano_osm(self, categoria, lat_actual, lon_actual, radio_metros=1500):
        """Busca el punto de interés más cercano (farmacia, hospital, banco, etc.) usando Overpass API."""
        tag_osm = None
        cat_lower = categoria.lower()
        if "farmacia" in cat_lower or "botica" in cat_lower or "remedio" in cat_lower:
            tag_osm = 'amenity="pharmacy"'
        elif "hospital" in cat_lower or "clinica" in cat_lower or "salud" in cat_lower:
            tag_osm = 'amenity="hospital"'
        elif "banco" in cat_lower or "cajero" in cat_lower or "atm" in cat_lower:
            tag_osm = 'amenity~"bank|atm"'
        elif "supermercado" in cat_lower or "super" in cat_lower or "mercado" in cat_lower:
            tag_osm = 'shop~"supermarket|convenience"'
        elif "parque" in cat_lower or "plaza" in cat_lower:
            tag_osm = 'leisure="park"'

        if tag_osm:
            try:
                # Query Overpass para encontrar nodos cercanos alrededor de la posición del usuario
                query = f"""
                [out:json][timeout:6];
                (
                  node[{tag_osm}](around:{radio_metros},{lat_actual},{lon_actual});
                  way[{tag_osm}](around:{radio_metros},{lat_actual},{lon_actual});
                );
                out center 5;
                """
                url = "https://overpass-api.de/api/interpreter"
                res = requests.post(url, data={"data": query}, timeout=6)
                if res.status_code == 200:
                    datos = res.json()
                    elementos = datos.get("elements", [])
                    if elementos:
                        mejor_elem = None
                        menor_dist = 999999
                        for elem in elementos:
                            e_lat = elem.get("lat") or elem.get("center", {}).get("lat")
                            e_lon = elem.get("lon") or elem.get("center", {}).get("lon")
                            if e_lat and e_lon:
                                dist, _ = self.calcular_distancia_y_rumbo(lat_actual, lon_actual, e_lat, e_lon)
                                if dist < menor_dist:
                                    menor_dist = dist
                                    mejor_elem = (e_lat, e_lon, elem.get("tags", {}).get("name") or categoria.capitalize(), dist)

                        if mejor_elem:
                            return mejor_elem
            except Exception as e:
                print(f"[LocationService] Overpass API falló: {e}")

        return None

    def buscar_y_establecer_destino(self, nombre_lugar, lat_actual, lon_actual):
        """Busca un lugar por nombre o categoría cercana y lo configura como destino activo."""
        print(f"[LocationService] Buscando destino: '{nombre_lugar}' cerca de ({lat_actual:.4f}, {lon_actual:.4f})...")

        # 1. Intentar primero búsqueda por categoría más cercana vía Overpass
        cercano = self.buscar_lugar_cercano_osm(nombre_lugar, lat_actual, lon_actual)
        if cercano:
            lat_dest, lon_dest, nombre_poi, dist = cercano
            return self.establecer_destino_por_coordenadas(lat_dest, lon_dest, nombre_poi, lat_actual, lon_actual)

        # 2. Búsqueda con Nominatim con viewbox acotado alrededor del usuario (~4 km)
        delta = 0.035
        left = lon_actual - delta
        right = lon_actual + delta
        top = lat_actual + delta
        bottom = lat_actual - delta

        try:
            consulta = nombre_lugar.strip()
            url = (
                "https://nominatim.openstreetmap.org/search?"
                f"q={requests.utils.quote(consulta)}&format=json&limit=3&accept-language=es"
                f"&viewbox={left},{top},{right},{bottom}&bounded=0"
            )
            headers = {"User-Agent": "BastonInteligenteApp/1.0 (accesibilidad visual)"}
            res = requests.get(url, headers=headers, timeout=6)
            
            if res.status_code == 200:
                data = res.json()
                if data and len(data) > 0:
                    # Encontrar el resultado más cercano al usuario de la lista devuelta
                    mejor_res = None
                    menor_dist = 999999
                    for item in data:
                        i_lat = float(item["lat"])
                        i_lon = float(item["lon"])
                        d, _ = self.calcular_distancia_y_rumbo(lat_actual, lon_actual, i_lat, i_lon)
                        if d < menor_dist:
                            menor_dist = d
                            mejor_res = (i_lat, i_lon, item.get("display_name", nombre_lugar).split(",")[0])

                    if mejor_res:
                        return self.establecer_destino_por_coordenadas(mejor_res[0], mejor_res[1], mejor_res[2], lat_actual, lon_actual)
        except Exception as e:
            print(f"[LocationService] Error al buscar en Nominatim: {e}")

        # 3. Fallback inteligente: Destino peatonal a 60 metros al frente
        lat_dest = lat_actual + 0.0005
        lon_dest = lon_actual + 0.0003
        return self.establecer_destino_por_coordenadas(lat_dest, lon_dest, nombre_lugar.capitalize(), lat_actual, lon_actual)

    def establecer_destino_por_coordenadas(self, lat, lon, nombre="Destino seleccionado", lat_actual=None, lon_actual=None):
        """Configura un destino a partir de coordenadas."""
        self.destino_lat = lat
        self.destino_lon = lon
        self.destino_nombre = nombre
        self.navegacion_activa = True
        
        if lat_actual is not None and lon_actual is not None:
            distancia, direccion = self.calcular_distancia_y_rumbo(lat_actual, lon_actual, self.destino_lat, self.destino_lon)
            self.ultima_distancia = distancia
            self.ultimo_rumbo = direccion
            return f"Ruta iniciada hacia {self.destino_nombre}. Se encuentra a unos {int(distancia)} metros hacia el {direccion}. Iniciando copiloto visual para guiar tus pasos."
        
        return f"Destino fijado: {self.destino_nombre}. Iniciando guiado asistido."

    def obtener_instruccion_guia(self, lat_actual, lon_actual):
        """Calcula la distancia actual y emite instrucciones de voz según el avance."""
        if not self.navegacion_activa or self.destino_lat is None:
            return None

        distancia, direccion = self.calcular_distancia_y_rumbo(lat_actual, lon_actual, self.destino_lat, self.destino_lon)
        self.ultima_distancia = distancia
        self.ultimo_rumbo = direccion

        # Si está a menos de 10 metros, ha llegado
        if distancia <= 10:
            nombre = self.destino_nombre
            self.cancelar_navegacion()
            return f"¡Has llegado a tu destino: {nombre}! La navegación ha finalizado."

        # Si está a menos de 25 metros
        if distancia <= 25:
            return f"Estás a solo {int(distancia)} metros de {self.destino_nombre}, justo al frente."

        return f"Avanza hacia el {direccion}. Faltan {int(distancia)} metros para {self.destino_nombre}."

    def cancelar_navegacion(self):
        """Detiene la guía activa."""
        self.navegacion_activa = False
        self.destino_lat = None
        self.destino_lon = None
        self.destino_nombre = None
        self.ultima_distancia = None
        self.ultimo_rumbo = ""

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

        puntos = ["Norte", "Noreste", "Este", "Sureste", "Sur", "Suroeste", "Oeste", "Noroeste"]
        indice = int((angulo + 22.5) / 45) % 8
        rumbo_cardinal = puntos[indice]

        return distancia, rumbo_cardinal
