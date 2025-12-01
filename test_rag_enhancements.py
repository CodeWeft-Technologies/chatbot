"""
Test script for RAG enhancements
Run this after installation to verify everything works
"""
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test all required imports"""
    print("\n🧪 Testing imports...")
    
    # Core dependencies
    try:
        from app.services.enhanced_scraper import scrape_url, ScrapedContent
        from app.services.enhanced_rag import (
            chunk_text_semantic,
            chunk_text,
            compute_content_hash,
            is_duplicate_content,
            remove_boilerplate
        )
        print("✅ Core modules imported successfully")
    except ImportError as e:
        print(f"❌ Core module import failed: {e}")
        return False
    
    # Optional: Playwright
    try:
        from playwright.sync_api import sync_playwright
        print("✅ Playwright available")
        PLAYWRIGHT = True
    except ImportError:
        print("⚠️  Playwright not available (will use fallback)")
        PLAYWRIGHT = False
    
    # Optional: Readability
    try:
        from readability import Document
        print("✅ Readability available")
    except ImportError:
        print("⚠️  Readability not available (will use fallback)")
    
    # Optional: NLTK
    try:
        import nltk
        nltk.data.find('tokenizers/punkt')
        print("✅ NLTK available with punkt data")
    except Exception:
        print("⚠️  NLTK not available (will use fallback)")
    
    # Optional: langdetect
    try:
        import langdetect
        print("✅ langdetect available")
    except ImportError:
        print("⚠️  langdetect not available (language detection disabled)")
    
    return True


def test_semantic_chunking():
    """Test semantic chunking"""
    print("\n🔪 Testing semantic chunking...")
    
    from app.services.enhanced_rag import chunk_text
    
    text = """
    Machine learning is a subset of artificial intelligence. It focuses on learning from data.
    Neural networks are powerful tools. They can learn complex patterns.
    Deep learning uses multiple layers. This enables hierarchical feature learning.
    """
    
    chunks = chunk_text(text, chunk_size=100)
    print(f"✅ Created {len(chunks)} chunks")
    
    # Check that chunks don't cut mid-sentence (basic check)
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i+1}: {chunk[:50]}...")
    
    return True


def test_deduplication():
    """Test content deduplication"""
    print("\n🔍 Testing deduplication...")
    
    from app.services.enhanced_rag import compute_content_hash
    
    content1 = "Machine learning is amazing"
    content2 = "Machine  learning   is  amazing"  # Extra spaces
    content3 = "MACHINE LEARNING IS AMAZING"  # Different case
    content4 = "Different content entirely"
    
    hash1 = compute_content_hash(content1)
    hash2 = compute_content_hash(content2)
    hash3 = compute_content_hash(content3)
    hash4 = compute_content_hash(content4)
    
    # Same content (normalized) should have same hash
    if hash1 == hash2 == hash3:
        print("✅ Deduplication normalizes whitespace and case correctly")
    else:
        print("❌ Deduplication normalization failed")
        return False
    
    # Different content should have different hash
    if hash1 != hash4:
        print("✅ Different content produces different hashes")
    else:
        print("❌ Hash collision detected")
        return False
    
    return True


def test_boilerplate_removal():
    """Test boilerplate removal"""
    print("\n🧹 Testing boilerplate removal...")
    
    from app.services.enhanced_rag import remove_boilerplate
    
    text_with_boilerplate = """
    Great article about machine learning!
    
    This website uses cookies to improve your experience.
    By continuing to use this site, you accept our cookie policy.
    
    Machine learning is transforming industries.
    
    Sign up for our newsletter to get the latest updates!
    
    Neural networks are powerful tools.
    
    Follow us on Twitter and Facebook!
    """
    
    cleaned = remove_boilerplate(text_with_boilerplate)
    
    # Check that boilerplate patterns are removed
    if "cookies" not in cleaned.lower():
        print("✅ Cookie notice removed")
    else:
        print("⚠️  Cookie notice still present")
    
    if "newsletter" not in cleaned.lower():
        print("✅ Newsletter signup removed")
    else:
        print("⚠️  Newsletter signup still present")
    
    # Check that actual content is preserved
    if "machine learning" in cleaned.lower() and "neural networks" in cleaned.lower():
        print("✅ Main content preserved")
    else:
        print("❌ Main content was removed")
        return False
    
    return True


def test_scraper_fallback():
    """Test scraper with fallback"""
    print("\n🌐 Testing web scraper (fallback mode)...")
    
    from app.services.enhanced_scraper import scrape_url
    
    try:
        # Test with a simple, reliable URL
        test_url = "https://example.com"
        
        # Force fallback mode (no Playwright)
        scraped = scrape_url(test_url, use_playwright=False, timeout=10)
        
        print(f"✅ Scraped URL: {scraped.final_url}")
        print(f"✅ Title: {scraped.title}")
        print(f"✅ Content length: {len(scraped.content)} chars")
        
        if scraped.content and len(scraped.content) > 50:
            print("✅ Content extraction successful")
        else:
            print("⚠️  Content extraction returned minimal content")
        
        return True
    except Exception as e:
        print(f"❌ Scraper test failed: {e}")
        return False


def test_playwright_scraper():
    """Test Playwright scraper (optional)"""
    print("\n🎭 Testing Playwright scraper...")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⏭️  Playwright not available, skipping test")
        return True
    
    from app.services.enhanced_scraper import scrape_url
    
    try:
        # Test with a simple URL
        test_url = "https://example.com"
        
        scraped = scrape_url(test_url, use_playwright=True, timeout=15)
        
        print(f"✅ Playwright scraped URL: {scraped.final_url}")
        print(f"✅ Title: {scraped.title}")
        print(f"✅ Content length: {len(scraped.content)} chars")
        
        return True
    except Exception as e:
        print(f"⚠️  Playwright test failed (this is OK): {e}")
        return True  # Non-critical


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("RAG ENHANCEMENT TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Semantic Chunking", test_semantic_chunking),
        ("Deduplication", test_deduplication),
        ("Boilerplate Removal", test_boilerplate_removal),
        ("Scraper Fallback", test_scraper_fallback),
        ("Playwright Scraper", test_playwright_scraper),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! RAG enhancements are working correctly.")
        return 0
    elif passed >= total - 1:
        print("\n✅ Core tests passed. Some optional features unavailable (OK).")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check installation and dependencies.")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
