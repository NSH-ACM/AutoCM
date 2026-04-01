# ═══════════════════════════════════════════════════════════════════════════
#  ACM — Dockerfile
#  Autonomous Constellation Manager | National Space Hackathon 2026
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: C++ Physics Engine Build ────────────────────────────────────
FROM ubuntu:22.04 AS cpp-builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential cmake python3 python3-dev python3-pip \
    && pip3 install pybind11 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY engine/ ./engine/

RUN cd engine && mkdir -p build && cd build \
    && (cmake .. && make -j$(nproc) || echo "[BUILD] C++ engine skipped") \
    && touch .keep

# ── Stage 2: Application ─────────────────────────────────────────────────
FROM ubuntu:22.04

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev \
    && pip3 install --no-cache-dir fastapi uvicorn pydantic \
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

# Ensure host-OS engine binaries (like .pyd or .so built on Windows/Mac) aren't mixed in
RUN rm -f ./core/autocm_engine*.so ./core/autocm_engine*.pyd

# Inject fresh Linux engine artifact from builder stage into core namespace
RUN find ./engine/build/ -name "autocm_engine*.so" -exec cp {} ./core/autocm_engine.so \; || true

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
