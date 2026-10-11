# Host build for the shuffler control stack SIL port.
#
#   cmake -B build
#   cmake --build build
#   ctest --test-dir build --output-on-failure
#
# The MATLAB C Caller build does NOT use this file - Simulink compiles
# core/ + sil/ itself (see sil/INSTRUCTIONS.md). This build exists for the
# golden-vector replay, the unit tests, and warning-free verification.
cmake_minimum_required(VERSION 3.13)
project(shuffler_sil C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(SHUF_WERROR "Treat warnings as errors" ON)
option(SHUF_ACCUM_DOUBLE
       "Design-rule-6 escape hatch: double integrator accumulator in the controller" OFF)

# Strict portability flags: -Wdouble-promotion / -Wfloat-conversion keep the
# code honest about float32-only arithmetic (AVR double == 32-bit, so any
# accidental double promotion would make SIL and PIL diverge).
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  set(SHUF_C_FLAGS -Wall -Wextra -Wpedantic -Wshadow -Wdouble-promotion
                   -Wfloat-conversion -Wconversion -Wundef)
  if(SHUF_WERROR)
    list(APPEND SHUF_C_FLAGS -Werror)
  endif()
endif()

# The control core lives in ONE place - 6_RTOS/ctrl_core - and is shared by the
# SIL build (here), the QSPICE C-block DLL and the STM32 firmware.
set(SHUF_CORE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../6_RTOS/ctrl_core)
add_library(shuffler_core STATIC
  ${SHUF_CORE_DIR}/shuffler_ctrl.c
  ${SHUF_CORE_DIR}/shuffler_supervisor.c
  ${SHUF_CORE_DIR}/shuffler_mppt.c
  ${SHUF_CORE_DIR}/shuffler_recon.c
  ${SHUF_CORE_DIR}/stack.c)
target_include_directories(shuffler_core PUBLIC ${SHUF_CORE_DIR})
target_compile_options(shuffler_core PRIVATE ${SHUF_C_FLAGS})
if(SHUF_ACCUM_DOUBLE)
  target_compile_definitions(shuffler_core PUBLIC SHUF_ACCUM_DOUBLE)
endif()

# Hardware configuration of the stack (reconstructed module currents): compiled
# here only to prove it builds warning-free; the firmware links its own copy.
add_library(shuffler_core_hw STATIC
  ${SHUF_CORE_DIR}/shuffler_ctrl.c
  ${SHUF_CORE_DIR}/shuffler_supervisor.c
  ${SHUF_CORE_DIR}/shuffler_mppt.c
  ${SHUF_CORE_DIR}/shuffler_recon.c
  ${SHUF_CORE_DIR}/stack.c)
target_include_directories(shuffler_core_hw PUBLIC ${SHUF_CORE_DIR})
target_compile_options(shuffler_core_hw PRIVATE ${SHUF_C_FLAGS})
target_compile_definitions(shuffler_core_hw PUBLIC STACK_RECON_IM=1)

# Compiled here only to prove the Simulink-facing wrappers build warning-free.
add_library(shuffler_sil_wrappers STATIC sil/sil_wrappers.c)
target_include_directories(shuffler_sil_wrappers PUBLIC sil)
target_link_libraries(shuffler_sil_wrappers PUBLIC shuffler_core)
target_compile_options(shuffler_sil_wrappers PRIVATE ${SHUF_C_FLAGS})

enable_testing()
add_subdirectory(test)
