#!/usr/bin/env python
"""Download required NLTK data for unstructured library."""
import nltk
import ssl
import sys

# Disable SSL verification for NLTK downloads if needed
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Download required NLTK packages
packages_to_download = [
    'averaged_perceptron_tagger',
    'punkt',
    'punkt_tab',
    'wordnet',
    'omw-1.4',
]

print("⬇️  Downloading NLTK data packages...")
for package in packages_to_download:
    try:
        nltk.download(package, quiet=True)
        print(f"✅ {package}")
    except Exception as e:
        print(f"⚠️  {package}: {e}", file=sys.stderr)

print("\n✅ NLTK data setup complete!")
