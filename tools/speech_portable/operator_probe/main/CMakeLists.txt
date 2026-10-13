idf_component_register(SRCS "main.cpp" INCLUDE_DIRS "."
    REQUIRES esp-dl esp_timer esp_psram esp_hw_support)
target_compile_features(${COMPONENT_LIB} PRIVATE cxx_std_17)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall)
