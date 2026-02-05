#!/usr/bin/env python
"""Railway-compatible startup script that reads PORT from environment."""
import os
import subprocess
import sys

# CRITICAL: Disable Unstructured model caching to prevent memory leaks
os.environ['UNSTRUCTURED_CACHE_DIR'] = '/tmp'
os.environ['TRANSFORMERS_CACHE'] = '/tmp'
os.environ['HF_HOME'] = '/tmp'
os.environ['TORCH_HOME'] = '/tmp'

port = os.getenv('PORT', '8000')

# Run uvicorn with the PORT from environment
subprocess.run([
    'uvicorn',
    'app.main:app',
    '--host', '0.0.0.0',
    '--port', port,
    '--workers', '1'
])
