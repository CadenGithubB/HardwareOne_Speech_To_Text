# HardwareOne's on-device speech-to-text engine as an ESP-IDF component (ESP32-P4 only).
#
# stt/ is HardwareOne's components/hardwareone/stt, unchanged (branch stt-speedups,
# commit 2e56063), with the model identity header of the model this repo ships.
# The three headers at this level stand in for the firmware's own:
#   System_STTLocal.h   the engine-facing control/stats types
#   Audio_VadPolicy.h   the adaptive VAD gate the segmenter uses (copied as is)
#   System_MemUtil.h    explicit PSRAM allocation (ps_alloc/ps_free), reimplemented
# It needs espressif/esp-dl 3.3.12 with ../../tools/esp-dl-3.3.12-hw1.patch applied
# (../../tools/prepare_esp_dl.py stages it; idf_component.yml points at the result).
if(NOT IDF_TARGET STREQUAL "esp32p4")
    idf_component_register()
    return()
endif()

option(HW1_STT_SPEAKER_LABELS "Also compile the speaker-label model (stt/speaker_model.h)" OFF)

set(hw1_stt_srcs
    stt/quartznet_runtime.cpp
    stt/quartznet_frontend.cpp
    stt/stt_lm.cpp
    stt/stt_dl_metadata.cpp
    System_MemUtil.cpp)
if(HW1_STT_SPEAKER_LABELS)
    list(APPEND hw1_stt_srcs stt/speaker_frontend.cpp stt/speaker_model.cpp)
endif()

idf_component_register(SRCS ${hw1_stt_srcs}
    INCLUDE_DIRS "." "stt"
    REQUIRES espressif__esp-dl esp_rom mbedtls esp_timer esp_hw_support esp_psram)
target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
# Same per-file options as HardwareOne: the frontend must not fuse multiply-adds
# (its features are hash-pinned against the host), inference code is built for speed.
set_source_files_properties(stt/quartznet_frontend.cpp PROPERTIES COMPILE_OPTIONS "-ffp-contract=off;-O2")
set_source_files_properties(stt/quartznet_runtime.cpp stt/stt_lm.cpp PROPERTIES COMPILE_OPTIONS "-O2")
if(HW1_STT_SPEAKER_LABELS)
    set_source_files_properties(stt/speaker_frontend.cpp stt/speaker_model.cpp PROPERTIES COMPILE_OPTIONS "-O2")
endif()
# One resident model per session (quartznet_runtime.h). Every translation unit
# that includes the runtime header must see the same value.
target_compile_definitions(${COMPONENT_LIB} PUBLIC HW1_STT_RESIDENT_MODEL=1)

# Compile only the ESP-DL operators the model graph uses.
idf_build_get_property(_hw1_build_components BUILD_COMPONENTS)
if("espressif__esp-dl" IN_LIST _hw1_build_components)
    idf_component_get_property(_hw1_dl_dir espressif__esp-dl COMPONENT_DIR)
elseif("esp-dl" IN_LIST _hw1_build_components)
    idf_component_get_property(_hw1_dl_dir esp-dl COMPONENT_DIR)
else()
    message(FATAL_ERROR "hw1_stt: espressif/esp-dl is not in the build")
endif()
if(NOT EXISTS "${_hw1_dl_dir}/hw1-esp-dl-override.json")
    message(FATAL_ERROR "hw1_stt: ${_hw1_dl_dir} is not the patched ESP-DL. Run firmware/tools/prepare_esp_dl.py first.")
endif()
include("${_hw1_dl_dir}/cmake/compile_register.cmake")
esp_dl_compile_add_yml("${CMAKE_CURRENT_LIST_DIR}/stt/quartznet.compile_req.yml")
if(HW1_STT_SPEAKER_LABELS)
    esp_dl_compile_add_yml("${CMAKE_CURRENT_LIST_DIR}/stt/speaker.compile_req.yml")
endif()
