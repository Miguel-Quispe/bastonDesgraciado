[app]
# (str) Title of your application
title = Baston Inteligente

# (str) Package name
package.name = bastonapp

# (str) Package domain (needed for android/ios packaging)
package.domain = org.baston

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json,txt,model,bin,pb,tflite,onnx

# (list) List of directory to exclude (let empty to not exclude anything)
source.exclude_dirs = tests, bin, .venv, .git, .github

# (str) Application versioning (method 1)
version = 1.0.0

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy,requests,qrcode,pillow,pyjnius,vosk,numpy

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 1

# (list) Permissions
android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, BLUETOOTH_SCAN, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, RECORD_AUDIO, INTERNET, CAMERA

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 24

# (str) Android NDK version to use
android.ndk = 25b

# (bool) Automatically accept SDK licenses
android.accept_sdk_license = True

# (list) List of Android architectures to build for
android.archs = arm64-v8a, armeabi-v7a

# (bool) Enable Android logcat filter
android.logcat_filters = *:S python:D

# (bool) Copy library instead of making a symlink
android.copy_libs = 1

[buildozer]
# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = off, 1 = on)
warn_on_root = 1
