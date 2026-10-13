#include <iostream>
#include <vector>
#include <chrono>
#include <cuda_runtime.h>
#include <cublas_v2.h>

int main(int argc, char** argv) {
    int duration_sec = (argc > 1) ? std::atoi(argv[1]) : 5;
    const int N = 4096;
    size_t size = (size_t)N * N * sizeof(half);

    half *d_A, *d_B, *d_C;
    cudaMalloc(&d_A, size);
    cudaMalloc(&d_B, size);
    cudaMalloc(&d_C, size);

    cublasHandle_t handle;
    cublasCreate(&handle);
    cublasSetMathMode(handle, CUBLAS_TENSOR_OP_MATH);

    half alpha = 1.0f;
    half beta = 0.0f;

    // Warmup
    for (int i = 0; i < 5; ++i) {
        cublasHgemm(handle, CUBLAS_OP_N, CUBLAS_OP_N,
                    N, N, N, &alpha, d_A, N, d_B, N, &beta, d_C, N);
    }
    cudaDeviceSynchronize();

    auto start = std::chrono::high_resolution_clock::now();
    int iterations = 0;
    while (true) {
        cublasHgemm(handle, CUBLAS_OP_N, CUBLAS_OP_N,
                    N, N, N, &alpha, d_A, N, d_B, N, &beta, d_C, N);
        iterations++;
        if (iterations % 50 == 0) {
            cudaDeviceSynchronize();
            auto now = std::chrono::high_resolution_clock::now();
            double elapsed = std::chrono::duration<double>(now - start).count();
            if (elapsed >= duration_sec) break;
        }
    }
    cudaDeviceSynchronize();
    auto end = std::chrono::high_resolution_clock::now();
    double total_sec = std::chrono::duration<double>(end - start).count();

    // 2 * N^3 operations per GEMM
    double ops = 2.0 * (double)N * (double)N * (double)N * iterations;
    double tflops = (ops / total_sec) / 1e12;

    std::cout << "ITERATIONS=" << iterations
              << " SECONDS=" << total_sec
              << " TFLOPS=" << tflops << std::endl;

    cublasDestroy(handle);
    cudaFree(d_A);
    cudaFree(d_B);
    cudaFree(d_C);
    return 0;
}
