import os
import sys
import traceback
from huggingface_hub import hf_hub_download

REPO = "bartowski/WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B-GGUF"
FILE = "WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B-Q4_K_M.gguf"
DIR = os.path.join(os.getcwd(), "data", "models")

print(f"--- Diagnostic Download Start ---")
print(f"Repo: {REPO}")
print(f"File: {FILE}")
print(f"Target Dir: {DIR}")

try:
    os.makedirs(DIR, exist_ok=True)
    print("Attempting download...")
    
    path = hf_hub_download(
        repo_id=REPO,
        filename=FILE,
        local_dir=DIR,
        local_dir_use_symlinks=False,
        resume_download=True,
        force_download=False
    )
    print(f"SUCCESS! Path: {path}")

except Exception as e:
    print("\n[!] FAILURE DETECTED [!]")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Message: {e}")
    print("\n--- Traceback ---")
    traceback.print_exc()
    
    # Check internet
    print("\n--- Connectivity Check ---")
    import socket
    try:
        host = "huggingface.co"
        port = 443
        socket.create_connection((host, port), 3)
        print(f"Socket connection to {host}:{port} - OK")
    except Exception as se:
        print(f"Socket connection to {host}:{port} - FAILED: {se}")