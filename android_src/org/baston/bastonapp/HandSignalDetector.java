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
import java.io.File;
import java.io.FileInputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.List;

/** Detecta una mano abierta localmente con proteccion total contra cierres o fallos nativos. */
public final class HandSignalDetector {
    private final HandLandmarker landmarker;
    private ByteBuffer modelBuffer; // Mantiene la referencia nativa en memoria para evitar liberacion por GC

    public HandSignalDetector(Context context, String modelPath) {
        BaseOptions.Builder baseOptionsBuilder = BaseOptions.builder();
        boolean loadedBuffer = false;
        try {
            File file = new File(modelPath);
            if (file.exists() && file.canRead()) {
                long length = file.length();
                if (length > 0 && length < 150 * 1024 * 1024) {
                    byte[] fileBytes = new byte[(int) length];
                    FileInputStream fis = new FileInputStream(file);
                    int totalRead = 0;
                    while (totalRead < fileBytes.length) {
                        int r = fis.read(fileBytes, totalRead, fileBytes.length - totalRead);
                        if (r <= 0) break;
                        totalRead += r;
                    }
                    fis.close();

                    modelBuffer = ByteBuffer.allocateDirect(fileBytes.length);
                    modelBuffer.order(ByteOrder.nativeOrder());
                    modelBuffer.put(fileBytes);
                    modelBuffer.rewind();
                    baseOptionsBuilder.setModelAssetBuffer(modelBuffer);
                    loadedBuffer = true;
                }
            }
        } catch (Throwable ignored) {
            loadedBuffer = false;
        }

        if (!loadedBuffer) {
            try {
                baseOptionsBuilder.setModelAssetPath(modelPath);
            } catch (Throwable ignored) {}
        }

        HandLandmarker tempLandmarker = null;
        try {
            HandLandmarker.HandLandmarkerOptions options = HandLandmarker.HandLandmarkerOptions.builder()
                    .setBaseOptions(baseOptionsBuilder.build())
                    .setNumHands(1)
                    .setMinHandDetectionConfidence(0.55f)
                    .setMinHandPresenceConfidence(0.55f)
                    .build();
            tempLandmarker = HandLandmarker.createFromOptions(context, options);
        } catch (Throwable t) {
            tempLandmarker = null;
        }
        this.landmarker = tempLandmarker;
    }

    public boolean isOpenPalmNv21(byte[] frame, int width, int height) {
        if (landmarker == null || frame == null || frame.length == 0 || width <= 0 || height <= 0) {
            return false;
        }
        Bitmap bitmap = null;
        try {
            YuvImage yuv = new YuvImage(frame, ImageFormat.NV21, width, height, null);
            ByteArrayOutputStream jpeg = new ByteArrayOutputStream();
            if (!yuv.compressToJpeg(new android.graphics.Rect(0, 0, width, height), 70, jpeg)) {
                return false;
            }
            byte[] bytes = jpeg.toByteArray();
            bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (bitmap == null) {
                return false;
            }
            MPImage image = new BitmapImageBuilder(bitmap).build();
            HandLandmarkerResult result = landmarker.detect(image);
            if (result == null) {
                return false;
            }
            List<List<NormalizedLandmark>> allLandmarks = result.landmarks();
            if (allLandmarks == null || allLandmarks.isEmpty()) {
                return false;
            }
            List<NormalizedLandmark> points = allLandmarks.get(0);
            if (points == null || points.size() < 21) {
                return false;
            }
            return hasFourExtendedFingers(points);
        } catch (Throwable t) {
            return false;
        } finally {
            if (bitmap != null) {
                try {
                    bitmap.recycle();
                } catch (Throwable ignored) {}
            }
        }
    }

    private boolean hasFourExtendedFingers(List<NormalizedLandmark> points) {
        try {
            if (points == null || points.size() < 21) {
                return false;
            }
            NormalizedLandmark wrist = points.get(0);
            if (wrist == null) return false;
            int[] bases = {5, 9, 13, 17};
            int[] tips = {8, 12, 16, 20};
            int extended = 0;
            for (int i = 0; i < tips.length; i++) {
                NormalizedLandmark base = points.get(bases[i]);
                NormalizedLandmark tip = points.get(tips[i]);
                if (base == null || tip == null) continue;
                float baseDistance = distance(wrist, base);
                float tipDistance = distance(wrist, tip);
                if (baseDistance > 0.02f && tipDistance > baseDistance * 1.25f) {
                    extended++;
                }
            }
            return extended >= 4;
        } catch (Throwable ignored) {
            return false;
        }
    }

    private float distance(NormalizedLandmark a, NormalizedLandmark b) {
        float dx = a.x() - b.x();
        float dy = a.y() - b.y();
        float dz = a.z() - b.z();
        return (float) Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    public void close() {
        try {
            if (landmarker != null) {
                landmarker.close();
            }
        } catch (Throwable ignored) {}
    }
}
