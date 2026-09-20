import threading
import time

class BluetoothManager:
    def __init__(self, mac_address="30:C9:22:32:F5:D6"):
        self.mac_address = mac_address
        self.conectado = False
        self.socket = None
        self.modo_simulacion = False
        self.conectando = False

    def conectar(self):
        """Inicia la conexión Bluetooth de forma segura sin bloquear la interfaz."""
        if self.conectado:
            return True

        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            UUID = autoclass('java.util.UUID')
            
            adapter = None
            try:
                adapter = BluetoothAdapter.getDefaultAdapter()
            except Exception as e:
                print(f"[BluetoothManager] No se pudo obtener BluetoothAdapter: {e}")
                
            if adapter is None or not adapter.isEnabled():
                print("[BluetoothManager] Bluetooth deshabilitado o no disponible en el dispositivo.")
                self.conectado = False
                return False

            device = adapter.getRemoteDevice(self.mac_address)
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            
            # Intento 1: Socket seguro SPP (Estándar)
            try:
                print("[BluetoothManager] Intentando conexión RFCOMM seguro...")
                self.socket = device.createRfcommSocketToServiceRecord(spp_uuid)
                self.socket.connect()
                self.conectado = True
                self.modo_simulacion = False
                print("[BluetoothManager] Conexión establecida exitosamente (RFCOMM seguro).")
                return True
            except Exception as e1:
                print(f"[BluetoothManager] Intento 1 (RFCOMM seguro) falló: {e1}. Probando RFCOMM inseguro...")

            # Intento 2: Socket inseguro SPP (Recomendado para ESP32 en Android)
            try:
                self.socket = device.createInsecureRfcommSocketToServiceRecord(spp_uuid)
                self.socket.connect()
                self.conectado = True
                self.modo_simulacion = False
                print("[BluetoothManager] Conexión establecida exitosamente (RFCOMM inseguro).")
                return True
            except Exception as e2:
                print(f"[BluetoothManager] Intento 2 (RFCOMM inseguro) falló: {e2}. Probando método de reflexión canal 1...")

            # Intento 3: Método oculto por reflexión en canal 1
            try:
                Integer = autoclass('java.lang.Integer')
                method = device.getClass().getMethod("createRfcommSocket", Integer.TYPE)
                self.socket = method.invoke(device, 1)
                self.socket.connect()
                self.conectado = True
                self.modo_simulacion = False
                print("[BluetoothManager] Conexión establecida exitosamente (Canal 1 reflexión).")
                return True
            except Exception as e3:
                print(f"[BluetoothManager] Intento 3 (Reflexión) falló: {e3}")
                raise e3

        except ImportError:
            print("[BluetoothManager] PyJNiUS no disponible (Entorno PC). Bluetooth no disponible.")
            self.conectado = False
            self.modo_simulacion = False
            return False
        except Exception as e:
            print(f"[BluetoothManager] Error al conectar Bluetooth ({self.mac_address}): {e}")
            self.conectado = False
            return False

    def conectar_async(self, callback_resultado=None):
        """Ejecuta la conexión en un hilo secundario para evitar cualquier congelamiento de la app."""
        if self.conectando:
            return

        def tarea_conexion():
            self.conectando = True
            exito = self.conectar()
            self.conectando = False
            if callback_resultado:
                callback_resultado(exito)

        hilo = threading.Thread(target=tarea_conexion, daemon=True)
        hilo.start()

    def escuchar_alertas_baston(self, callback_alerta, callback_estado=None):
        """Escucha tramas entrantes del ESP32 en un hilo independiente sin bloquear la app."""
        self._callback_estado = callback_estado

        def loop_lectura():
            while self.conectado:
                if self.modo_simulacion:
                    # En modo simulación no enviar alertas automáticas
                    time.sleep(5)
                    continue

                try:
                    if self.socket:
                        stream = self.socket.getInputStream()
                        if stream and stream.available() > 0:
                            bytes_data = stream.read()
                            mensaje = bytes_data.decode('utf-8', errors='ignore').strip()
                            if "OBSTACULO" in mensaje:
                                callback_alerta("Atención: Obstáculo detectado en línea recta")
                except Exception as e:
                    print(f"[BluetoothManager] Error en lectura Bluetooth: {e}")
                    self.conectado = False
                    if self._callback_estado:
                        self._callback_estado("Conexión con el bastón pausada.")
                    break

                time.sleep(0.3)

        if not hasattr(self, '_hilo_lectura') or not self._hilo_lectura.is_alive():
            self._hilo_lectura = threading.Thread(target=loop_lectura, daemon=True)
            self._hilo_lectura.start()

    def desconectar(self):
        """Cierra la conexión con el dispositivo Bluetooth."""
        self.conectado = False
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                print(f"[BluetoothManager] Error al cerrar socket: {e}")
            self.socket = None

    # Alias de compatibilidad
    escuchar_alertas_bastón = escuchar_alertas_baston
