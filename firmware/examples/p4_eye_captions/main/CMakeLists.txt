idf_component_register(SRCS "main.cpp"
    PRIV_REQUIRES hw1_stt fatfs sdmmc esp_driver_sdmmc esp_driver_i2s esp_driver_gpio esp_timer)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra)
