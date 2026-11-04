get_filename_component(STT_REPO "${CMAKE_CURRENT_LIST_DIR}/../../../../.." ABSOLUTE)
set(CAPTIONS_MAIN "${STT_REPO}/firmware/examples/p4_eye_captions/main")
idf_component_register(SRCS "replay.cpp" "speaker_prepare_probe.cpp" "${CAPTIONS_MAIN}/product.cpp"
    "${CAPTIONS_MAIN}/speaker_adapter.cpp" "${CAPTIONS_MAIN}/capture_diagnostics.cpp"
    INCLUDE_DIRS "${CAPTIONS_MAIN}"
    PRIV_REQUIRES hw1_stt hw1_transcript nvs_flash json fatfs sdmmc esp_driver_sdmmc
        esp_driver_i2s esp_driver_gpio esp_driver_usb_serial_jtag esp_timer)
idf_component_get_property(STT_LIBRARY hw1_stt COMPONENT_LIB)
target_compile_definitions(${STT_LIBRARY} PUBLIC HW1_STT_RUNTIME_DIAGNOSTICS=1)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -fstack-usage)
