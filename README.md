# 🦯 Bastón Inteligente - Asistente Autónomo Accesible para Personas con Discapacidad Visual

Aplicación móvil Android de alto contraste y accesible desarrollada en **Python/Kivy** diseñada para otorgar autonomía a personas con discapacidad visual. Las funciones locales priorizan el uso sin datos; Gemini, mapas y descripciones visuales avanzadas requieren internet.

Consulta [DOCUMENTACION_PROYECTO.md](DOCUMENTACION_PROYECTO.md) para el informe técnico, el estado de comandos y las limitaciones conocidas.

---

## 🌟 Características Principales

1. **🎙️ Palabra de Activación Personalizable y Persistente (Wake Word Dinámico):**
   - El usuario puede bautizar a su asistente con el nombre que prefiera (ej. *"Rayo"*, *"Asistente"*, *"Guía"*).
   - Simplemente diciendo: *"Cambiar nombre a Rayo"* o *"Llámate Rayo"*, la aplicación guarda el nombre de forma permanente.

2. **📖 Lectura de Documentos, Hojas y Etiquetas por Voz (`DocumentReader`):**
   - El usuario dice: *"Leer documento"*, *"Lee esta hoja"* o *"Lee la etiqueta"*.
   - La cámara toma la captura y la aplicación extrae el texto de recetas médicas, envases o hojas de papel y se lo lee por sintetizador de voz.

3. **📅 Agenda Personal y Recordatorios por Voz (`AgendaManager`):**
   - Gestión inteligente de notas, eventos y medicamentos agendados por dictado de voz.
   - Permite agregar recordatorios (*"Anotar tomar medicina a las 8 PM"*), consultar la lista (*"¿Qué tengo agendado hoy?"*) y borrar notas.

4. **♿ Confirmación Inmediata de Entrada (Accesibilidad para No Videntes):**
   - **Vibración háptica:** El teléfono emite una pulsación táctil al tocar la app para confirmar su inicio.
   - **Bienvenida por voz:** Anuncio automático inmediato: *"Aplicación iniciada. Asistente activo con el nombre [Nombre]. Te escucho."*

5. **🗺️ Navegación y Guiado Peatonal a un Destino:**
   - Permite solicitar rutas a destinos específicos por voz (ej. *"Guíame a la farmacia"*, *"Llévame al centro"*).
   - Calcula la distancia en metros (Haversine) y guía mediante rumbo cardinal (Norte, Sur, Este, Oeste).

6. **👁️ Visión Artificial y Detección de Obstáculos Offline (YOLO / TFLite):**
   - Análisis visual instantáneo usando modelos de **YOLOv8** para describir objetos y obstáculos cercanos en español.

7. **🦯 Conexión Bluetooth con Bastón Físico (ESP32):**
   - Conexión directa mediante puerto serie SPP con reconexión automática si se pierde la señal.

---

## 🗣️ Guía de Comandos de Voz

En la versión actual una palma abierta frente a la cámara trasera activa una única escucha. También se puede usar el botón de la aplicación como alternativa táctil.

| Función | Comandos de ejemplo | Qué hace la aplicación |
| :--- | :--- | :--- |
| **Cambiar Nombre** | *"Cambiar nombre a Rayo"*, *"Llámate Fénix"* | Cambia y guarda la palabra clave de activación de forma permanente. |
| **Lectura de Documentos** | *"Lee esta hoja"*, *"Leer documento"*, *"Lee la etiqueta"* | Captura una foto del papel o envase y lee todo su texto por voz. |
| **Anotar Recordatorio** | *"Guardar tomar medicina hasta el 25 de septiembre de 2027"* | Guarda un recordatorio local con fecha de creación y vencimiento. |
| **Consultar Agenda** | *"Ver agenda"*, *"¿Qué tengo agendado?"*, *"Mis recordatorios"* | Lee todos los eventos y notas agendados en voz alta. |
| **Limpiar Agenda** | *"Borrar agenda"*, *"Limpiar recordatorios"* | Elimina los recordatorios de tu agenda personal. |
| **Enlazar Bastón** | *"Rayo conéctate"*, *"Enlazar bastón"* | Inicia la conexión Bluetooth con el ESP32 y activa la escucha de alertas. |
| **Desconectar** | *"Rayo desconectar"* | Cierra la conexión Bluetooth de forma limpia. |
| **Guíame a un Lugar** | *"Rayo guíame a la farmacia"*, *"Llévame al parque"* | Calcula la ruta peatonal, la distancia y comienza a guiarte paso a paso por voz. |
| **Cancelar Ruta** | *"Rayo cancelar ruta"*, *"Detener guía"* | Detiene la navegación activa inmediatamente. |
| **Dónde Estoy** | *"Rayo dónde estoy"*, *"Mi ubicación"* | Obtiene tu posición GPS y te dice tu dirección en voz alta. |
| **Escanear Entorno**| *"Rayo mira"*, *"Foto"*, *"Qué hay al frente"* | Toma una foto y describe los obstáculos cercanos con su posición. |
| **Compartir App** | *"Rayo código QR"*, *"Comparte"* | Muestra el código QR en pantalla para compartir el proyecto. |
| **Saludo / Estado** | *"Hola Rayo"*, *"¿Estás ahí?"* | Confirma que el asistente está activo y listo para recibir órdenes. |

---

## 🏗️ Arquitectura del Proyecto

```text
BASTON/
├── .github/workflows/
│   └── build.yml               # Pipeline de compilación automática en la nube (GitHub Actions)
├── modules/
│   ├── agenda_manager.py       # Gestión de agenda personal y recordatorios por voz
│   ├── document_reader.py      # Captura y lectura por voz de documentos/hojas con la cámara
│   ├── bluetooth_manager.py    # Conexión SPP con ESP32 y reconexión automática
│   ├── speech_engine.py        # Motor Vosk offline, palabras clave dinámicas y TTS
│   ├── vision_analyzer.py      # Inferencia YOLO/TFLite y descripción espacial
│   └── location_service.py     # Servicio GPS y geocodificación de ruta
├── main.py                     # Aplicación Kivy, interfaz accesible y orquestación
├── buildozer.spec              # Configuración de empaquetado para Android
├── agenda_personal.json        # Archivo persistente de la agenda del usuario
├── config_asistente.json       # Nombre persistente del asistente
├── requirements.txt            # Dependencias de Python
└── README.md                   # Documentación oficial del proyecto
```

---

## 🧪 Pruebas en Computadora (PC)

Puedes probar los módulos directamente en tu computadora antes de compilar:

1. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Ejecutar la Aplicación:**
   ```bash
   python main.py
   ```

---

## 📦 Compilación del APK (Android)

El proyecto está listo para ser empaquetado con **Buildozer** o mediante **GitHub Actions**.
