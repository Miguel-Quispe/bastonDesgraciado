# Documentación Técnica - Bastón Inteligente

## Propósito

Bastón Inteligente es una aplicación Android accesible para apoyar a personas con discapacidad visual. Integra comandos de voz, alertas de un bastón ESP32, agenda local, cámara, ubicación y respuestas por voz.

La aplicación prioriza las funciones locales. Gemini, búsqueda de direcciones y descripciones visuales avanzadas requieren internet.

## Componentes

| Archivo | Función |
| --- | --- |
| `main.py` | Coordina la interfaz, comandos, cámara, agenda, GPS y Bluetooth. |
| `modules/speech_engine.py` | Reconocimiento de voz y síntesis de voz. |
| `modules/bluetooth_manager.py` | Enlace Bluetooth SPP con el ESP32. |
| `modules/agenda_manager.py` | Recordatorios locales persistentes. |
| `modules/vision_analyzer.py` | Cámara trasera, gesto de palma y visión. |
| `modules/document_reader.py` | Captura y lectura de documentos. |
| `modules/location_service.py` | GPS y direcciones. |
| `modules/ai_assistant.py` | Integración opcional con Gemini. |

La dirección MAC configurada para el bastón es `30:C9:22:32:F5:D6`.

## Forma de uso

La versión 1.0 usa la cámara trasera para detectar una palma abierta sin internet. Tras dos detecciones consecutivas, libera la cámara, espera a que Android active el micrófono y emite una vibración. Entonces el usuario pronuncia un único comando. Al terminar, el micrófono se cierra y la cámara vuelve al modo de espera.

Este flujo evita mantener el micrófono abierto y reduce el riesgo de que el asistente escuche su propia voz. Durante una captura para leer o describir, el detector de gestos queda detenido para que dos funciones no intenten usar la cámara al mismo tiempo.

## Comandos

| Función | Ejemplo | Internet | Estado |
| --- | --- | --- | --- |
| Saludo y ayuda | `Hola`, `¿estás ahí?` | No | Implementado. |
| Cambiar nombre | `Cambiar nombre a Rayo` | No | Implementado y persistente. |
| Guardar agenda | `Guardar tomar medicina hasta el 25 de septiembre de 2027` | No | Implementado; necesita fecha límite. |
| Consultar agenda | `Ver mi agenda` | No | Implementado; dice creación y vencimiento. |
| Limpiar agenda | `Limpiar agenda` | No | Implementado. |
| Conectar bastón | `Enlazar bastón` | No | Requiere Bluetooth activo y emparejamiento. |
| Alertas ESP32 | `OBSTACULO CERCA`, `OBSTACULO CASI CERCA`, `TOPANDO OBSTACULO` | No | Implementado; la app reproduce el texto recibido. |
| Hora y fecha | `¿Qué hora es?`, `¿Qué fecha es?` | No | Implementado. |
| QR | `Código QR` | No | Implementado. |
| Ubicación | `¿Dónde estoy?` | GPS; dirección normalmente requiere red | Implementado con respaldo en Santa Cruz, Bolivia. |
| Navegación | `Guíame a la farmacia` | Sí, para buscar destino | Requiere validación en recorridos reales. |
| Leer documento | `Lee este documento` | Gemini para lectura avanzada | La captura está implementada; OCR local completo no está empaquetado. |
| Describir frente | `¿Qué tengo al frente?` | No para objetos cotidianos; Gemini para detalle | EfficientDet Lite0 local identifica personas, sillas, mochilas, libros, computadoras, teclados y celulares, con posición y cercanía aproximada. Puertas, escalones, texto, lápices y reglas individuales pueden requerir Gemini. |
| Pregunta libre | Pregunta normal | Sí | Usa Gemini con una clave válida. |

## Agenda local

Los recordatorios se guardan en la memoria privada de la aplicación. Cada uno tiene descripción, fecha de creación automática y fecha límite indicada por el usuario. Los vencidos se eliminan al iniciar o consultar la agenda después de su fecha límite.

Fechas admitidas: `hasta mañana`, `hasta el 25 de septiembre de 2027` y `hasta 25/09/2027`.

## Protocolo ESP32

El ESP32 calcula las distancias con sus sensores. La app no interpreta las distancias: recibe y pronuncia el texto que envía el bastón. El receptor acumula los bytes de Bluetooth para aceptar mensajes completos aunque lleguen por partes o sin salto de línea.

## Pruebas y limitaciones

La versión 0.6 cerraba al cargar el modelo local de manos. La versión 0.7 corrigió la ruta del modelo. La versión 0.8 añade una espera entre liberar cámara y abrir micrófono, con una vibración que confirma el momento de hablar. La versión 0.9 evita la competencia entre reconocimiento y captura de cámara. La versión 1.0 incorpora detección local de objetos y modelos actuales de Gemini con certificados HTTPS incluidos.

Pendiente de validar en el celular: gesto de palma, escucha única, alertas reales del ESP32, lectura de documentos, cámara de entorno y funcionamiento prolongado con pantalla apagada.

Para reconocimiento sin internet, Android debe tener descargado un paquete de reconocimiento de voz en español. Si no existe, el reconocimiento puede usar la red del teléfono.
