import threading
import time
import unicodedata

class BluetoothManager:
    def __init__(self, mac_address="30:C9:22:32:F5:D6"):
        self.mac_address = mac_address
        self.conectado = False
        self.socket = None
        self.modo_simulacion = False
        self.conectando = False
        self.ultimo_error = ""
        self._buffer_entrada = bytearray()
        self._ultimo_byte_entrada = 0.0
        self._ultima_alerta = ""
        self._tiempo_ultima_alerta = 0.0
        self.desconexion_voluntaria = False

    def esta_conectado(self):
        """Retorna True si el socket Bluetooth está activo y conectado."""
        return bool(getattr(self, 'conectado', False))

    def _procesar_caracteres_baston(self, datos_bytes, callback_alerta):
        """
        Protocolo según los bloques de App Inventor del Bastón:
        - Carácter 'a': "Topando"
        - Carácter 'b': "Algo se detectó"
        - Carácter 'c': "Obstáculo cerca"
        """
        try:
            texto = datos_bytes.decode('utf-8', errors='ignore').strip()
        except Exception:
            texto = str(datos_bytes)

        if not texto:
            return

        ahora = time.monotonic()

        # Revisar cada carácter recibido del ESP32 / Arduino
        for c in texto:
            alerta = None
            if c == 'a' or c == 'A':
                alerta = "Topando."
            elif c == 'b' or c == 'B':
                alerta = "Algo se detectó."
            elif c == 'c' or c == 'C':
                alerta = "Obstáculo cerca."

            if alerta:
                # Evitar repetir la misma alerta dentro de 1.8 segundos
                if alerta == self._ultima_alerta and (ahora - self._tiempo_ultima_alerta) < 1.8:
                    continue
                self._ultima_alerta = alerta
                self._tiempo_ultima_alerta = ahora
                print(f"[BluetoothManager] Protocolo Bastón detectó '{c}' -> {alerta}")
                callback_alerta(alerta)

    def _fallar(self, mensaje):
        self.ultimo_error = mensaje
        self.conectado = False
        print(f"[BluetoothManager] {mensaje}")
        return False

    def _cerrar_socket_actual(self):
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None

    def _tiene_permiso_bluetooth_android(self):
        try:
            from android.permissions import check_permission, Permission
            return bool(check_permission(Permission.BLUETOOTH_CONNECT))
        except AttributeError:
            return True
        except Exception:
            return False

    def conectar(self):
        if self.conectado:
            return True

        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            BluetoothDevice = autoclass('android.bluetooth.BluetoothDevice')
            UUID = autoclass('java.util.UUID')

            if not self._tiene_permiso_bluetooth_android():
                return self._fallar("Falta permiso de dispositivos cercanos.")
            
            adapter = None
            try:
                adapter = BluetoothAdapter.getDefaultAdapter()
            except Exception:
                pass
                
            if adapter is None or not adapter.isEnabled():
                return self._fallar("Bluetooth está apagado.")

            try:
                adapter.cancelDiscovery()
            except Exception:
                pass

            device = adapter.getRemoteDevice(self.mac_address)
            if device.getBondState() != BluetoothDevice.BOND_BONDED:
                try:
                    device.createBond()
                except Exception:
                    pass
                return self._fallar(f"El bastón no está emparejado ({self.mac_address}).")

            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            
            # Intento 1: Inseguro (más compatible con ESP32 / HC-05)
            try:
                self.socket = device.createInsecureRfcommSocketToServiceRecord(spp_uuid)
                self.socket.connect()
                self.conectado = True
                self.modo_simulacion = False
                return True
            except Exception:
                self._cerrar_socket_actual()

            # Intento 2: Seguro Estándar
            try:
                self.socket = device.createRfcommSocketToServiceRecord(spp_uuid)
                self.socket.connect()
                self.conectado = True
                self.modo_simulacion = False
                return True
            except Exception:
                self._cerrar_socket_actual()

            # Intento 3: Canal 1 directo
            try:
                Integer = autoclass('java.lang.Integer')
                method = device.getClass().getMethod("createRfcommSocket", Integer.TYPE)
                self.socket = method.invoke(device, 1)
                self.socket.connect()
                self.conectado = True
                self.modo_simulacion = False
                return True
            except Exception as e3:
                raise e3

        except ImportError:
            self.ultimo_error = "Bluetooth nativo no disponible en PC."
            return False
        except (Exception, BaseException) as e:
            self._cerrar_socket_actual()
            return self._fallar(f"No se pudo conectar al bastón: {e}")

    def iniciar_auto_reconexion(self, callback_alerta, callback_estado=None):
        self._callback_alerta = callback_alerta
        self._callback_estado = callback_estado

        if hasattr(self, '_hilo_auto_reconexion') and self._hilo_auto_reconexion.is_alive():
            return

        def loop_auto():
            while True:
                try:
                    if not self.conectado and not self.conectando and not self.desconexion_voluntaria:
                        exito = self.conectar()
                        if exito:
                            if self._callback_estado:
                                self._callback_estado("Conectado al Bastón")
                            self.escuchar_alertas_baston(self._callback_alerta, self._callback_estado)
                except (Exception, BaseException) as err:
                    print(f"[BluetoothManager] Bucle auto-reconexión: {err}")
                time.sleep(5)

        self._hilo_auto_reconexion = threading.Thread(target=loop_auto, daemon=True)
        self._hilo_auto_reconexion.start()

    def conectar_async(self, callback_resultado=None):
        if self.conectando:
            return
        self.desconexion_voluntaria = False

        def tarea_conexion():
            self.conectando = True
            exito = self.conectar()
            self.conectando = False
            if callback_resultado:
                callback_resultado(exito)

        hilo = threading.Thread(target=tarea_conexion, daemon=True)
        hilo.start()

    def escuchar_alertas_baston(self, callback_alerta, callback_estado=None):
        self._callback_estado = callback_estado

        def loop_lectura():
            while self.conectado:
                if self.modo_simulacion:
                    time.sleep(4)
                    continue

                try:
                    if self.socket:
                        stream = self.socket.getInputStream()
                        if stream and stream.available() > 0:
                            # Leer bytes disponibles como en App Inventor (BytesDisponiblesParaRecibir)
                            cuantos = stream.available()
                            buffer_lectura = bytearray(cuantos)
                            leidos = stream.read(buffer_lectura, 0, cuantos)
                            if leidos > 0:
                                self._procesar_caracteres_baston(buffer_lectura[:leidos], callback_alerta)
                except Exception as e:
                    print(f"[BluetoothManager] Desconectado: {e}")
                    self.conectado = False
                    if self._callback_estado:
                        self._callback_estado("Bastón desconectado.")
                    break

                time.sleep(0.08) # Muestreo rápido para detectar 'a', 'b', 'c' al instante

        if not hasattr(self, '_hilo_lectura') or not self._hilo_lectura.is_alive():
            self._hilo_lectura = threading.Thread(target=loop_lectura, daemon=True)
            self._hilo_lectura.start()

    def desconectar(self):
        self.desconexion_voluntaria = True
        self.conectado = False
        self.conectando = False
        self._cerrar_socket_actual()
