import struct

model_path = "/root/model/qwen3.8/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q5_K_P.gguf"
with open(model_path, "rb") as f:
    magic = f.read(4)
    if magic != b"GGUF":
        print("Not GGUF")
        exit(1)
    version = struct.unpack("<I", f.read(4))[0]
    tensor_count = struct.unpack("<Q", f.read(8))[0]
    metadata_kv_count = struct.unpack("<Q", f.read(8))[0]
    print(f"GGUF v{version}, tensors: {tensor_count}, metadata: {metadata_kv_count}")

    def read_str():
        length = struct.unpack("<Q", f.read(8))[0]
        return f.read(length).decode("utf-8", errors="replace")

    def skip_val(val_type):
        if val_type in (0, 1, 7): # uint8, int8, bool
            f.seek(1, 1)
        elif val_type in (2, 3): # uint16, int16
            f.seek(2, 1)
        elif val_type in (4, 5, 6): # uint32, int32, float32
            f.seek(4, 1)
        elif val_type in (10, 11, 12): # uint64, int64, float64
            f.seek(8, 1)
        elif val_type == 8: # string
            l = struct.unpack("<Q", f.read(8))[0]
            f.seek(l, 1)
        elif val_type == 9: # array
            arr_type = struct.unpack("<I", f.read(4))[0]
            arr_len = struct.unpack("<Q", f.read(8))[0]
            for _ in range(arr_len):
                skip_val(arr_type)

    for i in range(metadata_kv_count):
        key = read_str()
        val_type = struct.unpack("<I", f.read(4))[0]
        if key == "tokenizer.chat_template":
            length = struct.unpack("<Q", f.read(8))[0]
            template = f.read(length).decode("utf-8", errors="replace")
            print("FOUND tokenizer.chat_template, length:", length)
            with open("/tmp/chat_template.jinja", "w", encoding="utf-8") as out:
                out.write(template)
            print("Saved to /tmp/chat_template.jinja")
            break
        else:
            skip_val(val_type)
