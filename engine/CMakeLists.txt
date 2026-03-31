cmake_minimum_required(VERSION 3.15)
project(autocm_engine)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find pybind11
find_package(pybind11 REQUIRED)

# Add source files
set(SOURCES
    propagator.cpp
    conjunction.cpp
    maneuver.cpp
    bindings.cpp
)

# Create Python extension module
pybind11_add_module(autocm_engine ${SOURCES})

# Set optimization flags
target_compile_options(autocm_engine PRIVATE -O3)

# Include directories
target_include_directories(autocm_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# Link libraries
target_link_libraries(autocm_engine PRIVATE pybind11::module)

# Enable testing
enable_testing()

# Create test executable
add_executable(test_propagator tests/test_propagator.cpp propagator.cpp)
target_link_libraries(test_propagator PRIVATE)

# Add test
add_test(NAME propagator_tests COMMAND test_propagator)
