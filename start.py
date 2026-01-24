#!/usr/bin/env python3
"""Entrypoint script for Railway deployment."""
import os
import subprocess
import sys

port = os.getenv("PORT", "8000")

try:
    port_int = int(port)
except ValueError:
    print(f"Error: PORT '{port}' is not a valid integer. Using default 8000.")
    port_int = 8000

cmd = [
    sys.executable,
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    str(port_int),
    "--workers",
    "1",
]

print(f"Starting uvicorn on port {port_int}...")
subprocess.run(cmd)
