# Compile the production implementation directly; experiments do not fork it.
# The engine is components/hardwareone/stt in a HardwareOne checkout and
# firmware/components/hw1_stt/stt in HardwareOne_Speech_To_Text.
get_filename_component(_hw1_repo_root "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
if(EXISTS "${_hw1_repo_root}/components/hardwareone/stt/quartznet_runtime.cpp")
    set(HW1_STT_SOURCE_DIR "${_hw1_repo_root}/components/hardwareone/stt")
else()
    set(HW1_STT_SOURCE_DIR "${_hw1_repo_root}/firmware/components/hw1_stt/stt")
endif()
idf_component_register(SRCS "main.cpp"
    "${HW1_STT_SOURCE_DIR}/quartznet_runtime.cpp"
    "${HW1_STT_SOURCE_DIR}/quartznet_frontend.cpp"
    INCLUDE_DIRS "." "${HW1_STT_SOURCE_DIR}" "${HW1_STT_SOURCE_DIR}/.."
    REQUIRES esp-dl esp_timer esp_psram esp_hw_support esp_rom mbedtls littlefs)
# The quoted identity include resolves beside the canonical runtime. Refuse a
# separately selected model directory whose generated identity does not match.
file(SHA256 "${HW1_STT_SOURCE_DIR}/stt_model_identity.h" _production_identity_sha)
file(SHA256 "${STT_MODEL_DIR}/stt_model_identity.h" _probe_identity_sha)
if(NOT _production_identity_sha STREQUAL _probe_identity_sha)
    message(FATAL_ERROR "STT_MODEL_DIR identity differs from the canonical production model")
endif()
# Exercise exactly the production model whitelist, not DL_COMPILE_ALL.
idf_component_get_property(_probe_dl_dir esp-dl COMPONENT_DIR)
include("${_probe_dl_dir}/cmake/compile_register.cmake")
esp_dl_compile_add_yml("${HW1_STT_SOURCE_DIR}/quartznet.compile_req.yml")
target_compile_features(${COMPONENT_LIB} PRIVATE cxx_std_17)
target_compile_definitions(${COMPONENT_LIB} PRIVATE HW1_STT_RUNTIME_DIAGNOSTICS=1)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -ffp-contract=off)
target_add_binary_data(${COMPONENT_LIB} "${STT_FIXTURE_DIR}/fixture0.pcm" BINARY)
target_add_binary_data(${COMPONENT_LIB} "${STT_FIXTURE_DIR}/fixture1.pcm" BINARY)
