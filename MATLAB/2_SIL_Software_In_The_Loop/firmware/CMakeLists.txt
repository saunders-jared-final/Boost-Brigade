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

add_library(shuffler_core STATIC
  core/shuffler_ctrl.c
  core/shuffler_supervisor.c
  core/shuffler_mppt.c
  core/stack.c)
target_include_directories(shuffler_core PUBLIC core)
target_compile_options(shuffler_core PRIVATE ${SHUF_C_FLAGS})
if(SHUF_ACCUM_DOUBLE)
  target_compile_definitions(shuffler_core PUBLIC SHUF_ACCUM_DOUBLE)
endif()

# Compiled here only to prove the Simulink-facing wrappers build warning-free.
add_library(shuffler_sil_wrappers STATIC sil/sil_wrappers.c)
target_include_directories(shuffler_sil_wrappers PUBLIC sil)
target_link_libraries(shuffler_sil_wrappers PUBLIC shuffler_core)
target_compile_options(shuffler_sil_wrappers PRIVATE ${SHUF_C_FLAGS})

enable_testing()
add_subdirectory(test)
