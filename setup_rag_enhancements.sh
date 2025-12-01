#!/bin/bash
# RAG Enhancement Setup Script
# This script installs all dependencies needed for the enhanced RAG features

set -e

echo "🚀 Setting up RAG enhancements..."
echo ""

# Check Python version
echo "Checking Python version..."
python --version
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt
echo "✅ Python dependencies installed"
echo ""

# Install Playwright browsers
echo "🌐 Installing Playwright browsers (for JS rendering)..."
echo "This may take a few minutes..."
playwright install chromium
echo "✅ Playwright chromium installed"
echo ""

# Download NLTK data
echo "📚 Downloading NLTK data (for semantic chunking)..."
python -c "import nltk; nltk.download('punkt', quiet=True); print('✅ NLTK punkt tokenizer downloaded')"
echo ""

# Test imports
echo "🧪 Testing imports..."
python << 'EOF'
import sys

# Test Playwright
try:
    from playwright.sync_api import sync_playwright
    print("✅ Playwright import successful")
except ImportError as e:
    print(f"⚠️  Playwright import failed: {e}")
    sys.exit(1)

# Test Readability
try:
    from readability import Document
    print("✅ Readability import successful")
except ImportError as e:
    print(f"⚠️  Readability import failed: {e}")
    sys.exit(1)

# Test langdetect
try:
    import langdetect
    print("✅ langdetect import successful")
except ImportError as e:
    print(f"⚠️  langdetect import failed: {e}")
    sys.exit(1)

# Test NLTK
try:
    import nltk
    nltk.data.find('tokenizers/punkt')
    print("✅ NLTK import and data successful")
except Exception as e:
    print(f"⚠️  NLTK check failed: {e}")
    sys.exit(1)

# Test enhanced modules
try:
    from app.services.enhanced_scraper import scrape_url
    from app.services.enhanced_rag import chunk_text_semantic
    print("✅ Enhanced modules import successful")
except ImportError as e:
    print(f"⚠️  Enhanced modules import failed: {e}")
    sys.exit(1)

print("")
print("🎉 All dependencies installed and tested successfully!")
EOF

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Update your .env file if needed"
echo "2. Start the server: uvicorn app.main:app --reload"
echo "3. Test with a URL ingestion request"
echo ""
echo "For detailed documentation, see:"
echo "  - RAG_ENHANCEMENT_SUMMARY.md"
echo "  - MIGRATION_NOTES.md"
