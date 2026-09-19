import os
import sys
from modules.vision_analyzer import VisionAnalyzer

def probar_vision_offline(imagen_path="test_entorno.jpg"):
    print(f"=== PRUEBA DE VISIÓN ARTIFICIAL OFFLINE (YOLO) ===")
    print(f"Analizando imagen: {imagen_path}")
    
    if not os.path.exists(imagen_path):
        print(f"Error: La imagen '{imagen_path}' no existe.")
        return

    analyzer = VisionAnalyzer()
    
    def callback(resultado):
        print("\n--- RESULTADO DE DETECCIÓN OFFLINE ---")
        print(resultado)
        print("--------------------------------------")
        
    analyzer.capturar_y_analizar(callback)

if __name__ == "__main__":
    img = sys.argv[1] if len(sys.argv) > 1 else "test_entorno.jpg"
    probar_vision_offline(img)
