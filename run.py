#!/usr/bin/env python
"""Railway-compatible startup script that reads PORT from environment."""
import os
import subprocess
import sys

port = os.getenv('PORT', '8000')

# Run uvicorn with the PORT from environment
subprocess.run([
    'uvicorn',
    'app.main:app',
    '--host', '0.0.0.0',
    '--port', port,
    '--workers', '1'
])
