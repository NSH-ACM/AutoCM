#!/bin/bash

# AutoCM Engine Build Script
# Builds the C++ physics engine and copies the Python extension to core/

set -e  # Exit on any error

echo "Building AutoCM Physics Engine..."

# Create build directory
mkdir -p build
cd build

# Configure with CMake
echo "Configuring with CMake..."
cmake .. -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR=/home/Code1/dev/temp/AutoCM/venv/lib/python3.13/site-packages/pybind11/share/cmake/pybind11

# Build the engine
echo "Building..."
make -j$(nproc)

# Find the built extension
echo "Locating built extension..."
EXTENSION_FILE=$(find . -name "autocm_engine*.so" | head -1)

if [ -z "$EXTENSION_FILE" ]; then
    echo "Error: Could not find autocm_engine.so file"
    exit 1
fi

echo "Found extension: $EXTENSION_FILE"

# Copy to core directory
echo "Copying to core/ directory..."
cp "$EXTENSION_FILE" "../../core/autocm_engine.so"

echo "Build complete! Extension copied to core/autocm_engine.so"

# Verify the copy
if [ -f "../../core/autocm_engine.so" ]; then
    echo "✓ Extension successfully copied to core/"
    ls -lh ../../core/autocm_engine.so
else
    echo "✗ Failed to copy extension"
    exit 1
fi
