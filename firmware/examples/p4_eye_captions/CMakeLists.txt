cmake_minimum_required(VERSION 3.16)
# Minimal on-device captions for the ESP32-P4X-EYE: microphone -> speech-to-text -> serial console.
# Build (ESP-IDF 5.5.5 exported, from this directory):
#   python3 ../../tools/prepare_esp_dl.py      # once: stage the patched ESP-DL 3.3.12
#   idf.py set-target esp32p4 build flash monitor
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(p4_eye_captions)
