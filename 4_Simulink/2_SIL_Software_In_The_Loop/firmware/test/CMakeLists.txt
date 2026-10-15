# Test executables: golden-vector replay + unit sanity suite.
# Test code is allowed stdio/double; it still builds with the strict flags
# minus -Wconversion/-Wdouble-promotion (double is intentional here).
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  set(SHUF_TEST_FLAGS -Wall -Wextra -Wpedantic -Wshadow)
  if(SHUF_WERROR)
    list(APPEND SHUF_TEST_FLAGS -Werror)
  endif()
endif()

add_executable(replay replay.c)
target_link_libraries(replay PRIVATE shuffler_core)
target_compile_options(replay PRIVATE ${SHUF_TEST_FLAGS})

add_executable(unit_tests unit_tests.c)
target_link_libraries(unit_tests PRIVATE shuffler_core)
target_compile_options(unit_tests PRIVATE ${SHUF_TEST_FLAGS})

add_executable(unit_tests_rt unit_tests.c)
target_link_libraries(unit_tests_rt PRIVATE shuffler_core_rt)
target_compile_options(unit_tests_rt PRIVATE ${SHUF_TEST_FLAGS})

# sin/fabs on some hosts still need libm explicitly
find_library(SHUF_LIBM m)
if(SHUF_LIBM)
  target_link_libraries(replay PRIVATE ${SHUF_LIBM})
  target_link_libraries(unit_tests PRIVATE ${SHUF_LIBM})
  target_link_libraries(unit_tests_rt PRIVATE ${SHUF_LIBM})
endif()

add_test(NAME unit_tests COMMAND unit_tests)
add_test(NAME unit_tests_rt COMMAND unit_tests_rt)
add_test(NAME replay_selftest COMMAND replay --selftest ${CMAKE_CURRENT_BINARY_DIR})

# AVR compile-only check (PIL forward-compatibility). Always registered so a
# missing toolchain shows up as SKIPPED in ctest output instead of the test
# silently not existing (avr_check.sh exits 2 when avr-gcc is absent).
add_test(NAME avr_compile_check
         COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/avr_check.sh
         WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/..)
set_tests_properties(avr_compile_check PROPERTIES SKIP_RETURN_CODE 2)
