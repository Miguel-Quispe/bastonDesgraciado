package org.baston.bastonapp;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.ImageFormat;
import android.graphics.YuvImage;

import com.google.mediapipe.framework.image.BitmapImageBuilder;
import com.google.mediapipe.framework.image.MPImage;
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark;
import com.google.mediapipe.tasks.core.BaseOptions;
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker;
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarkerResult;

import java.io.ByteArrayOutputStream;
import java.util.List;

/** Detecta una mano abierta localmente. No envía imágenes ni datos a Internet. */
public final class HandSignalDetector {
    private final HandLandmarker landmarker;

    public HandSignalDetector(Context context) {
        BaseOptions baseOptions = BaseOptions.builder()
                .setModelAssetPath("models/hand_landmarker.task")
                .build();
        HandLandmarker.HandLandmarkerOptions options = HandLandmarker.HandLandmarkerOptions.builder()
                .setBaseOptions(baseOptions)
                .setNumHands(1)
                .setMinHandDetectionConfidence(0.70f)
                .setMinHandPresenceConfidence(0.70f)
                .build();
        landmarker = HandLandmarker.createFromOptions(context, options);
    }

    public boolean isOpenPalmNv21(byte[] frame, int width, int height) {
        try {
            YuvImage yuv = new YuvImage(frame, ImageFormat.NV21, width, height, null);
            ByteArrayOutputStream jpeg = new ByteArrayOutputStream();
            if (!yuv.compressToJpeg(new android.graphics.Rect(0, 0, width, height), 75, jpeg)) {
                return false;
            }
            byte[] bytes = jpeg.toByteArray();
            Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (bitmap == null) {
                return false;
            }
            MPImage image = new BitmapImageBuilder(bitmap).build();
            HandLandmarkerResult result = landmarker.detect(image);
            if (result.landmarks().isEmpty()) {
                return false;
            }
            return hasFourExtendedFingers(result.landmarks().get(0));
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean hasFourExtendedFingers(List<NormalizedLandmark> points) {
        if (points.size() < 21) {
            return false;
        }
        NormalizedLandmark wrist = points.get(0);
        int[] bases = {5, 9, 13, 17};
        int[] tips = {8, 12, 16, 20};
        int extended = 0;
        for (int i = 0; i < tips.length; i++) {
            float baseDistance = distance(wrist, points.get(bases[i]));
            float tipDistance = distance(wrist, points.get(tips[i]));
            if (baseDistance > 0.02f && tipDistance > baseDistance * 1.55f) {
                extended++;
            }
        }
        return extended >= 4;
    }

    private float distance(NormalizedLandmark a, NormalizedLandmark b) {
        float dx = a.x() - b.x();
        float dy = a.y() - b.y();
        float dz = a.z() - b.z();
        return (float) Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    public void close() {
        landmarker.close();
    }
}
