// Shared speech qualification; camera/battery/IO/BLE configuration retained.
#pragma once
// P4X-EYE LCD, rotary wheel and three-button profile.
// Flattened from pinned p4_ble_roles/features.h because CMake reads literal defines.
// The inherited header hash is recorded in source-manifest.json.
// Core app, serial CLI, settings, LittleFS and encrypted mesh remain enabled.

#undef ENABLE_BLE_IDF_EXPERIMENTAL
#define ENABLE_BLE_IDF_EXPERIMENTAL 0

#undef NETWORK_FEATURE_LEVEL
#define NETWORK_FEATURE_LEVEL 3

#undef WEB_FEATURE_LEVEL
#define WEB_FEATURE_LEVEL 0  // headless: web UI left out so the LM decoder fits (user request 2026-09-29)

#undef CUSTOM_ENABLE_WEB_SENSORS
#define CUSTOM_ENABLE_WEB_SENSORS 0
#undef CUSTOM_ENABLE_WEB_BLUETOOTH
#define CUSTOM_ENABLE_WEB_BLUETOOTH 0
#undef CUSTOM_ENABLE_WEB_SPEECH
#define CUSTOM_ENABLE_WEB_SPEECH 0
#undef CUSTOM_ENABLE_WEB_ESPNOW
#define CUSTOM_ENABLE_WEB_ESPNOW 0
#undef CUSTOM_ENABLE_WEB_BOND
#define CUSTOM_ENABLE_WEB_BOND 0
#undef CUSTOM_ENABLE_WEB_MQTT
#define CUSTOM_ENABLE_WEB_MQTT 0
#undef CUSTOM_ENABLE_WEB_GAMES
#define CUSTOM_ENABLE_WEB_GAMES 0
#undef CUSTOM_ENABLE_WEB_MAPS
#define CUSTOM_ENABLE_WEB_MAPS 0
#undef CUSTOM_ENABLE_WEB_BATTERY
#define CUSTOM_ENABLE_WEB_BATTERY 0
#undef CUSTOM_ENABLE_WEB_R1_HEALTH
#define CUSTOM_ENABLE_WEB_R1_HEALTH 0 // Omit optional web panel to fit continuous STT; ring support stays enabled.

#undef ENABLE_HTTPS
#define ENABLE_HTTPS 0

#undef ENABLE_MQTT
#define ENABLE_MQTT 0

#undef I2C_FEATURE_LEVEL
#define I2C_FEATURE_LEVEL 0

#undef DISPLAY_TYPE
#define DISPLAY_TYPE 4

#undef INPUT_DEVICE_TYPE
#define INPUT_DEVICE_TYPE 3

#undef XIAO_ESP32S3_SENSE_ENABLED
#define XIAO_ESP32S3_SENSE_ENABLED 0

#undef ENABLE_CAMERA_SENSOR
#define ENABLE_CAMERA_SENSOR 1

#undef ENABLE_MICROPHONE_SENSOR
#define ENABLE_MICROPHONE_SENSOR 1

#undef ENABLE_BATTERY_MONITOR
#define ENABLE_BATTERY_MONITOR 1

#undef ENABLE_NEOPIXEL
#define ENABLE_NEOPIXEL 0

#undef ENABLE_BLUETOOTH
#define ENABLE_BLUETOOTH 1

#undef ENABLE_G2_GLASSES
#define ENABLE_G2_GLASSES 1

#undef ENABLE_R1_HEALTH
#define ENABLE_R1_HEALTH 1

#undef ENABLE_G2_TESTSUITE
#define ENABLE_G2_TESTSUITE 0

#undef ENABLE_ESP_SR
#define ENABLE_ESP_SR 1

#undef ENABLE_EDGE_IMPULSE
#define ENABLE_EDGE_IMPULSE 0

#undef ENABLE_AUTOMATION
#define ENABLE_AUTOMATION 0

#undef ENABLE_UART_HOST_LINK
#define ENABLE_UART_HOST_LINK 0

#undef ENABLE_RASPBERRY_PI_HOST_POWER
#define ENABLE_RASPBERRY_PI_HOST_POWER 0

#undef ENABLE_RASPBERRY_PI_HOST_FAN
#define ENABLE_RASPBERRY_PI_HOST_FAN 0

#undef ENABLE_BONDED_MODE
#define ENABLE_BONDED_MODE 0

#undef ENABLE_GAMES
#define ENABLE_GAMES 0

#undef ENABLE_WEB_GAME_DARKROOM
#define ENABLE_WEB_GAME_DARKROOM 0

#undef ENABLE_LLM_BACKEND
#define ENABLE_LLM_BACKEND 0

#undef ENABLE_LLM_SOURCE_ONBOARD
#define ENABLE_LLM_SOURCE_ONBOARD 0

#undef ENABLE_LLM_SOURCE_CM5
#define ENABLE_LLM_SOURCE_CM5 0

#undef ENABLE_MAPS
#define ENABLE_MAPS 0

#undef HW_BOARD_P4X_EYE
#define HW_BOARD_P4X_EYE 1
#undef ENABLE_GPIO_ENCODER_BUTTONS
#define ENABLE_GPIO_ENCODER_BUTTONS 1

// LCD and input only; neither SD/MMC nor another card backend is enabled.
#undef ENABLE_SDMMC_CARD
#define ENABLE_SDMMC_CARD 1  // 15x5 test build: model lives on the microSD card
#undef ENABLE_SD_CARD
#define ENABLE_SD_CARD 1

// Preserve the existing application and LittleFS partition boundaries.
#undef HW1_SR_MODELS_IN_FILESYSTEM
#define HW1_SR_MODELS_IN_FILESYSTEM 1

// Fully local buffered transcription, independent of UART/Pi.
#undef ENABLE_LOCAL_STT
#define ENABLE_LOCAL_STT 1

// 15x5 test build: ~15 MB model on the card (too large for LittleFS).
#undef HW1_STT_MODEL_PATH
#define HW1_STT_MODEL_PATH "/sd/STT Models/quartznet15x5.p4.stt"
