idf_component_register(SRCS "main.cpp" "product.cpp" "speaker_adapter.cpp" "overlap_adapter.cpp" "segment_recorder.cpp" "capture_diagnostics.cpp"
    PRIV_REQUIRES hw1_stt hw1_transcript nvs_flash json fatfs sdmmc esp_driver_sdmmc esp_driver_i2s esp_driver_gpio esp_driver_usb_serial_jtag esp_timer)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra)

if(CONFIG_CAPTIONS_STREAM_METRICS)
    set_property(SOURCE main.cpp capture_diagnostics.cpp APPEND PROPERTY COMPILE_OPTIONS -fstack-usage)
endif()
