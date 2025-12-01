# RAG Enhancement Setup Script (Windows)
# This script installs all dependencies needed for the enhanced RAG features

Write-Host "🚀 Setting up RAG enhancements..." -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
python --version
Write-Host ""

# Install Python dependencies
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
Write-Host "✅ Python dependencies installed" -ForegroundColor Green
Write-Host ""

# Install Playwright browsers
Write-Host "🌐 Installing Playwright browsers (for JS rendering)..." -ForegroundColor Yellow
Write-Host "This may take a few minutes..." -ForegroundColor Gray
try {
    playwright install chromium
    Write-Host "✅ Playwright chromium installed" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Playwright installation failed: $_" -ForegroundColor Red
    Write-Host "You can continue without Playwright (system will use fallback scraping)" -ForegroundColor Yellow
}
Write-Host ""

# Download NLTK data
Write-Host "📚 Downloading NLTK data (for semantic chunking)..." -ForegroundColor Yellow
python -c "import nltk; nltk.download('punkt', quiet=True); print('✅ NLTK punkt tokenizer downloaded')"
Write-Host ""

# Test imports
Write-Host "🧪 Testing imports..." -ForegroundColor Yellow
$testScript = @'
import sys

# Test Playwright
try:
    from playwright.sync_api import sync_playwright
    print("✅ Playwright import successful")
except ImportError as e:
    print(f"⚠️  Playwright import failed: {e}")
    print("   System will use fallback scraping")

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
'@

python -c $testScript

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Update your .env file if needed"
Write-Host "2. Start the server: uvicorn app.main:app --reload"
Write-Host "3. Test with a URL ingestion request"
Write-Host ""
Write-Host "For detailed documentation, see:" -ForegroundColor Cyan
Write-Host "  - RAG_ENHANCEMENT_SUMMARY.md"
Write-Host "  - MIGRATION_NOTES.md"
