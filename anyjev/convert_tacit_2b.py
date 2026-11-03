import json
import subprocess
import sys
from pathlib import Path

model_dir = Path("/root/deepseek-harness/models/Tacit-2B_hf")
config_file = model_dir / "config.json"

if config_file.exists():
    with open(config_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    print("Original mtp_num_hidden_layers:", cfg.get("mtp_num_hidden_layers"))
    if "text_config" in cfg and "mtp_num_hidden_layers" in cfg["text_config"]:
        cfg["text_config"]["mtp_num_hidden_layers"] = 0
    cfg["mtp_num_hidden_layers"] = 0
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    print("Updated config.json: mtp_num_hidden_layers set to 0")

f16_path = "/root/deepseek-harness/models/Tacit-2B-f16.gguf"
q4_path = "/root/deepseek-harness/models/Tacit-2B-Q4_K_M.gguf"

print("\n[1/2] Converting Tacit-2B Safetensors to GGUF F16...")
cmd_convert = [
    "/root/venv_convert/bin/python3",
    "/root/llama_src/convert_hf_to_gguf.py",
    str(model_dir),
    "--outfile", f16_path,
    "--outtype", "f16",
    "--no-nextn",
]
res = subprocess.run(cmd_convert)
if res.returncode != 0:
    print("Convert failed!")
    sys.exit(1)

print("\n[2/2] Quantizing GGUF F16 -> Q4_K_M...")
cmd_quant = [
    "/root/llama.cpp/bin/llama-quantize",
    f16_path,
    q4_path,
    "Q4_K_M",
]
res2 = subprocess.run(cmd_quant)
if res2.returncode != 0:
    print("Quantize failed!")
    sys.exit(1)

Path(f16_path).unlink(missing_ok=True)
print(f"\nSuccess! Final model saved to: {q4_path}")
