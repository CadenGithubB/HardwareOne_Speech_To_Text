get_filename_component(STT_REPO "${CMAKE_CURRENT_LIST_DIR}/../../../../.." ABSOLUTE)
set(CAPTIONS_MAIN "${STT_REPO}/firmware/examples/p4_eye_captions/main")
idf_component_register(SRCS "precision.cpp" "${CAPTIONS_MAIN}/product.cpp"
    "${CAPTIONS_MAIN}/speaker_adapter.cpp" "${CAPTIONS_MAIN}/capture_diagnostics.cpp"
    INCLUDE_DIRS "${CAPTIONS_MAIN}" "../.."
    PRIV_REQUIRES hw1_stt hw1_transcript nvs_flash json fatfs sdmmc esp_driver_sdmmc
        esp_driver_i2s esp_driver_gpio esp_driver_usb_serial_jtag esp_timer)
# IDF's early requirements pass returns from idf_component_register before
# application cache variables are available. Validate assets in the real pass.
if(NOT HW1_PRECISION_DELTA OR NOT EXISTS "${HW1_PRECISION_DELTA}")
    message(FATAL_ERROR "Supply a reviewed private HW1_PRECISION_DELTA file")
endif()
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -fstack-usage)
target_add_binary_data(${COMPONENT_LIB} "${HW1_PRECISION_DELTA}" BINARY RENAME_TO "precision_delta")
if(HW1_PRECISION_TRACE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE HW1_PRECISION_TRACE=1)
endif()
idf_component_get_property(precision_dl_dir espressif__esp-dl COMPONENT_DIR)
include("${precision_dl_dir}/cmake/compile_register.cmake")
esp_dl_compile_add_yml("${CMAKE_CURRENT_LIST_DIR}/block14.compile_req.yml")
