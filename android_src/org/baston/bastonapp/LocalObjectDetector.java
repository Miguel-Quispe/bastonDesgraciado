package org.baston.bastonapp;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.RectF;

import com.google.mediapipe.framework.image.BitmapImageBuilder;
import com.google.mediapipe.framework.image.MPImage;
import com.google.mediapipe.tasks.components.containers.Category;
import com.google.mediapipe.tasks.components.containers.Detection;
import com.google.mediapipe.tasks.vision.objectdetector.ObjectDetector;
import com.google.mediapipe.tasks.vision.objectdetector.ObjectDetectorResult;

import java.io.File;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Detecta objetos en una foto localmente. La imagen nunca sale del teléfono. */
public final class LocalObjectDetector {
    private final ObjectDetector detector;
    private static final Map<String, String> TRADUCCIONES = new HashMap<>();

    static {
        TRADUCCIONES.put("person", "persona");
        TRADUCCIONES.put("bicycle", "bicicleta");
        TRADUCCIONES.put("car", "auto");
        TRADUCCIONES.put("motorcycle", "motocicleta");
        TRADUCCIONES.put("bus", "autobús");
        TRADUCCIONES.put("truck", "camión");
        TRADUCCIONES.put("chair", "silla");
        TRADUCCIONES.put("couch", "sofá");
        TRADUCCIONES.put("bed", "cama");
        TRADUCCIONES.put("dining table", "mesa");
        TRADUCCIONES.put("tv", "televisor");
        TRADUCCIONES.put("laptop", "computadora portátil");
        TRADUCCIONES.put("cell phone", "celular");
        TRADUCCIONES.put("bottle", "botella");
        TRADUCCIONES.put("cup", "taza");
        TRADUCCIONES.put("backpack", "mochila");
        TRADUCCIONES.put("handbag", "bolso");
        TRADUCCIONES.put("suitcase", "maleta");
        TRADUCCIONES.put("book", "libro");
        TRADUCCIONES.put("dog", "perro");
        TRADUCCIONES.put("cat", "gato");
        TRADUCCIONES.put("stop sign", "señal de alto");
    }

    public LocalObjectDetector(Context context, String modelPath) throws Exception {
        detector = ObjectDetector.createFromFile(context, new File(modelPath));
    }

    public String describeImage(String imagePath) {
        Bitmap bitmap = BitmapFactory.decodeFile(imagePath);
        if (bitmap == null) {
            return "";
        }
        if (bitmap.getConfig() != Bitmap.Config.ARGB_8888) {
            bitmap = bitmap.copy(Bitmap.Config.ARGB_8888, false);
        }
        MPImage image = new BitmapImageBuilder(bitmap).build();
        ObjectDetectorResult result = detector.detect(image);
        List<Detection> detections = result.detections();
        if (detections.isEmpty()) {
            return "";
        }

        StringBuilder message = new StringBuilder("Visión local: ");
        int included = 0;
        for (Detection detection : detections) {
            if (detection.categories().isEmpty()) {
                continue;
            }
            Category category = detection.categories().get(0);
            if (category.score() < 0.45f) {
                continue;
            }
            if (included > 0) {
                message.append(", ");
            }
            String label = category.categoryName();
            message.append(TRADUCCIONES.containsKey(label) ? TRADUCCIONES.get(label) : label);
            message.append(" ").append(position(detection.boundingBox(), bitmap.getWidth()));
            included++;
            if (included == 3) {
                break;
            }
        }
        return included == 0 ? "" : message.toString() + ".";
    }

    private String position(RectF box, int imageWidth) {
        float center = box.centerX() / imageWidth;
        if (center < 0.35f) {
            return "a la izquierda";
        }
        if (center > 0.65f) {
            return "a la derecha";
        }
        return "al frente";
    }

    public void close() {
        detector.close();
    }
}
