"""
Test script to detect if a website needs JavaScript rendering (Playwright)
Usage: python test_js_detection.py <url>
"""
import sys
import requests
from bs4 import BeautifulSoup

def test_url(url: str):
    """Compare static vs JS rendering to detect if Playwright is needed"""
    
    print(f"\n🔍 Testing: {url}\n")
    print("=" * 70)
    
    # Test 1: Static HTML (requests + BeautifulSoup)
    print("\n1️⃣  Static HTML (requests + BeautifulSoup)")
    print("-" * 70)
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Remove scripts and styles
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()
        
        static_text = soup.get_text(separator=" ", strip=True)
        static_length = len(static_text)
        
        print(f"✅ Content length: {static_length:,} characters")
        print(f"📝 Preview: {static_text[:200]}...")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return
    
    # Test 2: Check for common JS framework markers
    print("\n2️⃣  JavaScript Framework Detection")
    print("-" * 70)
    
    js_indicators = {
        "React": ["react", "reactDOM", "root"],
        "Vue": ["vue", "v-app", "v-cloak"],
        "Angular": ["ng-app", "ng-controller", "angular"],
        "Next.js": ["__NEXT_DATA__", "_next"],
        "Nuxt": ["__NUXT__"],
        "SPA": ["<div id=\"root\"></div>", "<div id=\"app\"></div>"]
    }
    
    found_frameworks = []
    html_lower = response.text.lower()
    
    for framework, indicators in js_indicators.items():
        if any(indicator.lower() in html_lower for indicator in indicators):
            found_frameworks.append(framework)
    
    if found_frameworks:
        print(f"⚠️  Detected JS frameworks: {', '.join(found_frameworks)}")
        print("   → This site LIKELY needs Playwright for full content")
    else:
        print("✅ No major JS frameworks detected")
        print("   → Static scraping should work fine")
    
    # Test 3: Check for empty root divs
    print("\n3️⃣  Empty Container Check")
    print("-" * 70)
    
    root_selectors = ["#root", "#app", "#__next", "[data-reactroot]"]
    empty_roots = []
    
    for selector in root_selectors:
        try:
            element = soup.select_one(selector)
            if element and len(element.get_text(strip=True)) < 50:
                empty_roots.append(selector)
        except:
            pass
    
    if empty_roots:
        print(f"⚠️  Found empty/minimal containers: {', '.join(empty_roots)}")
        print("   → Content is likely rendered by JavaScript")
        print("   → USE PLAYWRIGHT for this site")
    else:
        print("✅ No empty root containers found")
        print("   → Content appears to be server-rendered")
    
    # Test 4: Playwright comparison (if available)
    print("\n4️⃣  Playwright Comparison")
    print("-" * 70)
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=15000, wait_until="networkidle")
            page.wait_for_timeout(1000)
            
            playwright_text = page.inner_text("body")
            playwright_length = len(playwright_text)
            
            browser.close()
            
            print(f"✅ Playwright content length: {playwright_length:,} characters")
            
            # Compare lengths
            difference = playwright_length - static_length
            percent_diff = (difference / static_length * 100) if static_length > 0 else 0
            
            print(f"\n📊 Comparison:")
            print(f"   Static:     {static_length:>10,} chars")
            print(f"   Playwright: {playwright_length:>10,} chars")
            print(f"   Difference: {difference:>10,} chars ({percent_diff:+.1f}%)")
            
            if percent_diff > 50:
                print(f"\n🚨 RECOMMENDATION: USE PLAYWRIGHT")
                print(f"   → Playwright extracted {percent_diff:.0f}% more content!")
                print(f"   → This site heavily relies on JavaScript rendering")
            elif percent_diff > 20:
                print(f"\n⚠️  RECOMMENDATION: Consider using Playwright")
                print(f"   → {percent_diff:.0f}% more content with JS rendering")
            else:
                print(f"\n✅ RECOMMENDATION: Static scraping is sufficient")
                print(f"   → Only {percent_diff:.0f}% difference")
            
    except ImportError:
        print("⏭️  Playwright not installed - skipping comparison")
        print("   Install with: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"⚠️  Playwright test failed: {e}")
    
    # Final recommendation
    print("\n" + "=" * 70)
    print("📌 FINAL RECOMMENDATION")
    print("=" * 70)
    
    if found_frameworks or empty_roots:
        print("🎭 USE PLAYWRIGHT - This site needs JavaScript rendering")
        print("   In your code:")
        print("   scraped = scrape_url(url, use_playwright=True)")
    else:
        print("🚀 USE STATIC SCRAPING - Faster and sufficient")
        print("   In your code:")
        print("   scraped = scrape_url(url, use_playwright=False)")
    
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_js_detection.py <url>")
        print("\nExamples:")
        print("  python test_js_detection.py https://example.com")
        print("  python test_js_detection.py https://react-app.vercel.app")
        sys.exit(1)
    
    url = sys.argv[1]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    test_url(url)
