import os
import sys
import time
import warnings

# Suppress upstream library deprecation notices
warnings.filterwarnings("ignore", message=".*Deprecated Feature.*")
warnings.filterwarnings("ignore", message=".*deprecated.*")
os.environ["PYTHONWARNINGS"] = "ignore"

import subprocess
import webbrowser
import threading
from pathlib import Path


def open_browser():
    time.sleep(1.5)
    url = "http://localhost:8000"
    print(f"\n[+] Opening YouTube Clipper Pro in browser: {url}")
    webbrowser.open(url)


def main():
    print("=" * 60)
    print("          🎬 YouTube Clipper Pro Starting...          ")
    print("=" * 60)

    print(f"[+] Python Version: {sys.version.split()[0]}")

    # Launch browser thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Run uvicorn server
    try:
        import uvicorn
        uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
    except ImportError:
        print("[!] Uvicorn not installed. Please run: py -m pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()
