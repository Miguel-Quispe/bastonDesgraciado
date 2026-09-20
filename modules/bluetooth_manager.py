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

    @staticmethod
    def _normalizar_mensaje(mensaje):
        texto = unicodedata.normalize('NFD', mensaje.upper())
        return ''.join(caracter for caracter in texto if unicodedata.category(caracter) != 'Mn')

    def _procesar_alerta_recibida(self, callback_alerta):
        """Convierte solo los textos que manda el ESP32 en avisos de voz."""
        if not self._buffer_entrada:
            return

        texto = bytes(self._buffer_entrada).decode('utf-8', errors='ignore').strip()
        self._buffer_entrada.clear()
        mensaje = self._normalizar_mensaje(texto)

        if "TOPANDO OBSTACULO" in mensaje:
            alerta = "Atención: estás topando un obstáculo."
        elif "OBSTACULO CASI CERCA" in mensaje:
            alerta = "Atención: obstáculo casi cerca."
        elif "OBSTACULO CERCA" in mensaje:
            alerta = "Atención: obstáculo cerca."
        else:
            # No interpretar distancias: si el ESP32 manda una frase distinta, leerla tal cual.
            alerta = texto

        if not alerta:
            return
        ahora = time.monotonic()
        if alerta == self._ultima_alerta and ahora - self._tiempo_ultima_alerta < 3.0:
            return
        self._ultima_alerta = alerta
        self._tiempo_ultima_alerta = ahora
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
            # Android anterior a 12 no usa BLUETOOTH_CONNECT como permiso en tiempo de ejecución.
            return True
        except Exception as e:
            print(f"[BluetoothManager] No se pudo comprobar permiso Bluetooth: {e}")
            return False

    def conectar(self):
        """Inicia la conexión Bluetooth de forma segura sin bloquear la interfaz."""
        if self.conectado:
            return True

        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            BluetoothDevice = autoclass('android.bluetooth.BluetoothDevice')
            UUID = autoclass('java.util.UUID')

            if not self._tiene_permiso_bluetooth_android():
                return self._fallar("Falta el permiso de dispositivos cercanos para conectar el bastón.")
            
            adapter = None
            try:
                adapter = BluetoothAdapter.getDefaultAdapter()
            except Exception as e:
                print(f"[BluetoothManager] No se pudo obtener BluetoothAdapter: {e}")
                
            if adapter is None or not adapter.isEnabled():
                return self._fallar("Bluetooth está apagado o no está disponible.")

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
                return self._fallar(
                    f"El bastón {self.mac_address} no está emparejado. Acepta el emparejamiento Bluetooth y vuelve a decir conectar bastón."
                )
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
                self._cerrar_socket_actual()

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
                self._cerrar_socket_actual()

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
            self.ultimo_error = "Bluetooth nativo no disponible en la PC."
            print(f"[BluetoothManager] {self.ultimo_error}")
            self.modo_simulacion = False
            return False
        except Exception as e:
            self._cerrar_socket_actual()
            return self._fallar(f"No se pudo conectar con el bastón {self.mac_address}: {e}")

    def iniciar_auto_reconexion(self, callback_alerta, callback_estado=None):
        """Inicia un hilo en segundo plano que reintenta conectar automáticamente al Bastón cada 6 segundos."""
        self._callback_alerta = callback_alerta
        self._callback_estado = callback_estado

        if hasattr(self, '_hilo_auto_reconexion') and self._hilo_auto_reconexion.is_alive():
            return

        def loop_auto():
            while True:
                if not self.conectado and not self.conectando:
                    print("[BluetoothManager Auto] Intentando conectar automáticamente al Bastón ESP32...")
                    exito = self.conectar()
                    if exito:
                        if self._callback_estado:
                            self._callback_estado("Conectado al Bastón ESP32 (30:C9:22:32:F5:D6)")
                        self.escuchar_alertas_baston(self._callback_alerta, self._callback_estado)
                time.sleep(6)

        self._hilo_auto_reconexion = threading.Thread(target=loop_auto, daemon=True)
        self._hilo_auto_reconexion.start()

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
                            # InputStream.read() entrega un entero (un byte), no una cadena.
                            # Acumular la trama evita cerrar una conexión válida al primer dato del ESP32.
                            dato = stream.read()
                            if isinstance(dato, int):
                                if dato >= 0:
                                    self._buffer_entrada.append(dato & 0xFF)
                            else:
                                self._buffer_entrada.extend(bytes(dato))
                            self._ultimo_byte_entrada = time.monotonic()
                            if b'\n' in self._buffer_entrada or b'\r' in self._buffer_entrada:
                                self._procesar_alerta_recibida(callback_alerta)
                        elif self._buffer_entrada and time.monotonic() - self._ultimo_byte_entrada > 0.25:
                            # El ESP32 puede mandar las frases sin salto de línea. Una pausa corta marca el final.
                            self._procesar_alerta_recibida(callback_alerta)

                        if len(self._buffer_entrada) > 256:
                            self._buffer_entrada.clear()
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
