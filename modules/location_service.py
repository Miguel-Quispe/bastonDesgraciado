import requests

class LocationService:
    def __init__(self, api_key_mapbox="pk.eyJ1IjoiZGVtb3VzZXIiLCJhIjoiY2xleGFtcGxlMDAwMDAwMDAwMDAwMDAwMCJ9.example"):
        self.api_key = api_key_mapbox

    def obtener_coordenadas(self):
        """Obtiene la ubicación GPS nativa del dispositivo (LocationManager) o coordenadas simuladas."""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            activity = PythonActivity.mActivity
            
            location_manager = activity.getSystemService(Context.LOCATION_SERVICE)
            location = location_manager.getLastKnownLocation('gps')
            
            if location is None:
                # Si GPS no responde, intentar con red/wifi
                location = location_manager.getLastKnownLocation('network')

            if location:
                return location.getLatitude(), location.getLongitude()
            
            print("[LocationService] GPS nativo sin última ubicación conocida. Utilizando coordenadas de respaldo.")
            return -17.7833, -63.1821
        except Exception as e:
            print(f"[LocationService] Lectura GPS nativa no disponible ({e}). Usando coordenadas de simulación.")
            # Coordenadas de prueba (Santa Cruz de la Sierra)
            return -17.7833, -63.1821

    def consultar_direccion_mapbox(self, lat, lon):
        """Geocodificación inversa llamando al API Geocoding de Mapbox o fallback en caso de error."""
        if not self.api_key or "TU_MAPBOX_KEY" in self.api_key or "example" in self.api_key:
            return f"Latitud {lat:.4f}, Longitud {lon:.4f} (Zona Centro, Av. Principal)"

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
