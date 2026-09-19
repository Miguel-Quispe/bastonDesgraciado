import threading
import time

class BluetoothManager:
    def __init__(self, mac_address="30:C9:22:32:F5:D6"):
        self.mac_address = mac_address
        self.conectado = False
        self.socket = None
        self.modo_simulacion = False

    def conectar(self):
        """Inicia la conexión Bluetooth (nativa en Android vía PyJNiUS o simulación en PC)."""
        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            UUID = autoclass('java.util.UUID')
            
            adapter = BluetoothAdapter.getDefaultAdapter()
            if adapter is None or not adapter.isEnabled():
                print("[BluetoothManager] Bluetooth deshabilitado o no disponible en el dispositivo.")
                self.conectado = False
                return False

            device = adapter.getRemoteDevice(self.mac_address)
            
            # UUID estándar de Puerto Serie SPP
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            self.socket = device.createRfcommSocketToServiceRecord(spp_uuid)
            self.socket.connect()
            self.conectado = True
            self.modo_simulacion = False
            print("[BluetoothManager] Conexión establecida exitosamente con el ESP32.")
            return True
        except ImportError:
            print("[BluetoothManager] PyJNiUS no disponible (Entorno de desarrollo/Escritorio). Usando modo simulación.")
            self.conectado = True
            self.modo_simulacion = True
            return True
        except Exception as e:
            print(f"[BluetoothManager] Error al conectar Bluetooth ({self.mac_address}): {e}")
            self.conectado = False
            return False

    def escuchar_alertas_baston(self, callback_alerta, callback_estado=None):
        """Escucha tramas entrantes del ESP32 (ej. alertas de proximidad) en un hilo independiente.
        Si se pierde la conexión, intenta reconectar automáticamente."""
        self._callback_estado = callback_estado

        def loop_lectura():
            intentos_reconexion = 0
            while True:  # Bucle principal del hilo
                if not self.conectado:
                    if intentos_reconexion > 0:
                        if self._callback_estado:
                            self._callback_estado("Intentando reconectar al bastón...")
                        time.sleep(3) # Esperar antes de reintentar
                        if self.conectar():
                            if self._callback_estado:
                                self._callback_estado("Reconectado al bastón")
                            intentos_reconexion = 0
                        else:
                            intentos_reconexion += 1
                            continue
                    else:
                        break # Si no estaba conectado desde un principio, salir

                if self.modo_simulacion:
                    # Simulación para pruebas en escritorio
                    time.sleep(10)
                    if self.conectado:
                        callback_alerta("Atención: Obstáculo detectado en línea recta (Simulación)")
                    continue

                try:
                    stream = self.socket.getInputStream()
                    if stream.available() > 0:
                        bytes_data = stream.read()
                        mensaje = bytes_data.decode('utf-8', errors='ignore').strip()
                        if "OBSTACULO" in mensaje:
                            callback_alerta("Atención: Obstáculo detectado en línea recta")
                except Exception as e:
                    print(f"[BluetoothManager] Desconexión o error en flujo Bluetooth: {e}")
                    self.conectado = False
                    if self._callback_estado:
                        self._callback_estado("Se perdió la conexión. Reconectando...")
                    intentos_reconexion = 1 # Iniciar reconexión

                time.sleep(0.2)

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
