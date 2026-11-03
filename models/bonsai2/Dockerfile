FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

ARG CUDA_ARCHITECTURES="70"
ENV DEBIAN_FRONTEND=noninteractive
ENV LIBRARY_PATH="/usr/local/cuda/lib64/stubs:${LIBRARY_PATH}"
ENV LD_LIBRARY_PATH="/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    ninja-build \
    build-essential \
    ca-certificates \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 -b prism https://github.com/PrismML-Eng/llama.cpp.git llama.cpp

WORKDIR /src/llama.cpp
RUN cmake -B build -G Ninja \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHITECTURES}" \
    -DGGML_CUDA_FA_ALL=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_EXE_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" \
    -DCMAKE_SHARED_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" \
    && cmake --build build --target llama-server -j$(nproc) \
    && (find build -name "*.so*" -exec cp -u {} build/bin/ \; 2>/dev/null || true)

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libgomp1 \
    libcurl4 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /src/llama.cpp/build/bin/ /app/

ENV LD_LIBRARY_PATH="/app:${LD_LIBRARY_PATH}"
ENV PATH="/app:${PATH}"
EXPOSE 8080

ENTRYPOINT ["/app/llama-server"]
