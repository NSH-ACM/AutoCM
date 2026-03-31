cmake_minimum_required(VERSION 3.18)
project(acm_engine VERSION 4.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Optimisation Flags ───────────────────────────────────────────────────────
if(MSVC)
  set(CMAKE_CXX_FLAGS_RELEASE "/O2 /Oy /GL /DNDEBUG /fp:fast")
  set(CMAKE_CXX_FLAGS_DEBUG   "/Od /Zi")
else()
  set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -ffast-math -funroll-loops -DNDEBUG")
  set(CMAKE_CXX_FLAGS_DEBUG   "-O0 -g -fsanitize=address")
endif()

# ── OpenMP (optional) ────────────────────────────────────────────────────────
find_package(OpenMP QUIET)
if(OpenMP_CXX_FOUND)
  message(STATUS "OpenMP found — parallel propagation enabled")
endif()

# ── pybind11 ─────────────────────────────────────────────────────────────────
find_package(pybind11 QUIET)
if(NOT pybind11_FOUND)
  execute_process(
    COMMAND python -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE PYBIND11_FOUND_VIA_PIP
  )
  if(PYBIND11_FOUND_VIA_PIP EQUAL 0)
    list(APPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKE_DIR}")
    find_package(pybind11 REQUIRED)
  else()
    message(FATAL_ERROR
      "pybind11 not found. Install it with:  pip install pybind11")
  endif()
endif()

# ── Build the extension ───────────────────────────────────────────────────────
# All .cpp files are compiled together into a single Python extension module.
pybind11_add_module(acm_engine
  propagator.cpp
  conjunction.cpp
  maneuver.cpp
  bindings.cpp
)

target_include_directories(acm_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

if(OpenMP_CXX_FOUND)
  target_link_libraries(acm_engine PRIVATE OpenMP::OpenMP_CXX)
endif()

target_compile_definitions(acm_engine PRIVATE
  PYBIND11_COMPILER_TYPE=""
  PYBIND11_STDLIB=""
  PYBIND11_BUILD_ABI=""
)

# ── Output to build/ subfolder ────────────────────────────────────────────────
set_target_properties(acm_engine PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build"
)

message(STATUS "ACM Engine: C++17 multi-file build configured")
message(STATUS "  Modules: propagator, conjunction, maneuver, bindings")
message(STATUS "  Release flags: ${CMAKE_CXX_FLAGS_RELEASE}")
