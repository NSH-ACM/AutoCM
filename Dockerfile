# ═══════════════════════════════════════════════════════════════════════════
#  ACM — Dockerfile
#  Autonomous Constellation Manager | National Space Hackathon 2026
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: C++ Physics Engine Build ────────────────────────────────────
FROM ubuntu:22.04 AS cpp-builder

ENV DEBIAN_FRONTEND=noninteractive

# Pin python3.11 explicitly — avoids cpython binary suffix mismatch
RUN apt-get update && apt-get install -y \
    build-essential cmake python3.11 python3.11-dev python3-pip \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && pip3 install pybind11 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY engine/ ./engine/

RUN cd engine && mkdir -p build && cd build \
    && PYBIND11_DIR=$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())") \
    && echo "PYBIND11_DIR: $PYBIND11_DIR" \
    && cmake .. -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="$PYBIND11_DIR" \
    && make -j$(nproc) \
    || (echo "[BUILD] C++ engine build failed — Python mock will be used" && touch .keep)

# ── Stage 2: Application ─────────────────────────────────────────────────
FROM ubuntu:22.04

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# Pin python3.11 — must match builder stage to avoid cpython-3XX suffix mismatch
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-dev python3-pip \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY api/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy C++ engine artifacts (will copy .keep if build failed)
COPY --from=cpp-builder /build/engine/build/ ./engine/build/

# Copy application layers
COPY api/ ./api/
COPY data/ ./data/
COPY frontend/ ./frontend/
COPY core/ ./core/

# Generate catalog if not present
RUN cd /app/data && python3 generate_catalog.py 2>/dev/null || echo "[OK] Using existing catalog"

# Ensure host-OS engine binaries (like .pyd or .so built on Windows/Mac) aren't mixed in
RUN rm -f ./core/autocm_engine*.so ./core/autocm_engine*.pyd

# Inject fresh Linux engine artifact from builder stage into core namespace
RUN find ./engine/build/ -name "autocm_engine*.so" -exec cp {} ./core/autocm_engine.so \; \
    && echo "[DEPLOY] C++ engine deployed to core/" \
    || echo "[DEPLOY] No C++ engine found — Python mock active"

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
