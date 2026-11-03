#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

local_dir = "/root/deepseek-harness/models/Tacit-4B_hf"
f16_gguf = "/root/deepseek-harness/models/Tacit-4B-f16.gguf"
q4_gguf = "/root/deepseek-harness/models/Tacit-4B-Q4_K_M.gguf"

print(f"=== Step 3: Converting HF model to F16 GGUF ===", flush=True)
cmd_convert = [
    "/root/venv_convert/bin/python3",
    "/root/llama_src/convert_hf_to_gguf.py",
    local_dir,
    "--outfile", f16_gguf,
    "--outtype", "f16",
]
res = subprocess.run(cmd_convert)
if res.returncode != 0:
    print("GGUF Conversion failed!", file=sys.stderr)
    sys.exit(1)

print(f"=== Step 4: Quantizing F16 GGUF -> Q4_K_M ===", flush=True)
quantize_bin = "/root/llama.cpp/bin/llama-quantize"
cmd_quant = [quantize_bin, f16_gguf, q4_gguf, "Q4_K_M"]
res2 = subprocess.run(cmd_quant)
if res2.returncode != 0:
    print("Quantization failed!", file=sys.stderr)
    sys.exit(1)

print(f"=== Step 5: Cleanup intermediate F16 ===", flush=True)
Path(f16_gguf).unlink(missing_ok=True)
print(f"Success! Final model saved: {q4_gguf} ({os.path.getsize(q4_gguf) / (1024*1024):.2f} MB)", flush=True)
