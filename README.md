# 🦯 Bastón Inteligente - Asistente Autónomo para Personas con Discapacidad Visual

Aplicación móvil Android accesible y de alto contraste desarrollada en **Python/Kivy** diseñada para otorgar autonomía a personas con discapacidad visual. El sistema es **100% autónomo y offline**, garantizando privacidad, rapidez y **cero consumo de datos móviles**.

---

## 🌟 Características Principales

1. **🎙️ Escucha Continua 100% Offline (Vosk API):**
   - No consume internet ni megas móviles.
   - Escucha en segundo plano constantemente mediante captura nativa de micrófono (`AudioRecord`).
   - Responde únicamente cuando el usuario le habla o usa palabras de activación como *"Bastón"*, *"Oye Bastón"* o *"Hola Bastón"*.

2. **👁️ Visión Artificial y Detección de Obstáculos Offline (YOLO / TFLite):**
   - Análisis visual instantáneo usando modelos ligeros de **YOLOv8** (3 a 6 MB).
   - Detecta más de 80 objetos cotidianos (personas, vehículos, escalones, bancos, conos de obra, perros, etc.).
   - Traduce las detecciones a coordenadas espaciales y proximidad en español:
     *Ejemplo: «Atención: Cono de obra en el centro al frente (cerca), persona a la izquierda».*

3. **🦯 Conexión Bluetooth con Bastón Físico (ESP32):**
   - Conexión directa mediante puerto serie SPP.
   - **Reconexión automática**: Si el bastón se apaga o pierde señal temporalmente, la aplicación reintenta enlazarse cada 3 segundos y avisa por voz al usuario.

4. **🎧 Detección Inteligente de Auriculares:**
   - Comprueba si tienes auriculares conectados (Bluetooth o cable) y sugiere ponértelos para mantener la privacidad de tus avisos.

5. **📍 Ubicación y Geocodificación GPS:**
   - Consulta las coordenadas GPS del dispositivo y las traduce a direcciones físicas legibles.

6. **📱 Compartir mediante Código QR:**
   - Generación de código QR en pantalla de alto contraste para compartir la aplicación fácilmente.

---

## 🗣️ Guía de Comandos de Voz

Al abrir la aplicación, el micrófono estará siempre activo. Puedes decir los siguientes comandos directamente:

| Función | Comandos de ejemplo | Qué hace la aplicación |
| :--- | :--- | :--- |
| **Enlazar Bastón** | *"Bastón conéctate"*, *"Enlazar bastón"* | Inicia la conexión Bluetooth con el ESP32 y activa la escucha de alertas. |
| **Desconectar** | *"Bastón desconectar"* | Cierra la conexión Bluetooth de forma limpia. |
| **Guíame a un Lugar** | *"Bastón guíame a la farmacia"*, *"Llévame al parque"* | Calcula la ruta peatonal, la distancia y comienza a guiarte paso a paso por voz. |
| **Cancelar Ruta** | *"Bastón cancelar ruta"*, *"Detener guía"* | Detiene la navegación activa inmediatamente. |
| **Dónde Estoy** | *"Bastón dónde estoy"*, *"Mi ubicación"* | Obtiene tu posición GPS y te dice tu dirección en voz alta. |
| **Escanear Entorno**| *"Bastón mira"*, *"Foto"*, *"Qué hay al frente"* | Toma una foto y describe los obstáculos cercanos con su posición. |
| **Compartir App** | *"Bastón código QR"*, *"Comparte"* | Muestra el código QR en pantalla para compartir el proyecto. |
| **Saludo / Estado** | *"Hola bastón"*, *"¿Estás ahí?"* | Confirma que el asistente está activo y listo para recibir órdenes. |

---

## 🏗️ Arquitectura del Proyecto

```text
BASTON/
├── .github/workflows/
│   └── build.yml               # Pipeline de compilación automática en la nube (GitHub Actions)
├── modules/
│   ├── bluetooth_manager.py    # Conexión SPP con ESP32 y reconexión automática
│   ├── speech_engine.py        # Motor Vosk offline, captura de audio y TTS
│   ├── vision_analyzer.py      # Inferencia YOLO/TFLite y descripción espacial
│   └── location_service.py     # Servicio GPS y geocodificación
├── main.py                     # Aplicación Kivy y orquestación general
├── buildozer.spec              # Configuración de empaquetado para Android
├── test_yolo_offline.py        # Script para pruebas de visión en PC
├── test_entorno.jpg            # Imagen de prueba para detección de obstáculos
└── requirements.txt            # Dependencias del proyecto
```

---

## 🧪 Pruebas en Computadora (PC)

Puedes probar los módulos directamente en tu computadora antes de compilar:

1. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Probar la Visión Artificial con YOLO:**
   ```bash
   python test_yolo_offline.py test_entorno.jpg
   ```

3. **Ejecutar la Interfaz Gráfica:**
   ```bash
   python main.py
   ```

---

## 📦 Compilación Automática del APK (Android)

Este repositorio cuenta con **GitHub Actions** configurado para compilar el APK automáticamente:

1. Haz un `push` a la rama `main`.
2. Ve a la pestaña **Actions** de este repositorio en GitHub.
3. Al finalizar el flujo, descarga el archivo **`BastonApp-Debug-APK`** de la sección *Artifacts*.
4. Instala el `.apk` resultante en tu dispositivo Android.
