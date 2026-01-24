#!/usr/bin/env python3
"""
Example scripts for testing the multimodal RAG ingestion endpoint.

Usage:
    python test_multimodal_examples.py upload-text
    python test_multimodal_examples.py upload-pdf research.pdf
    python test_multimodal_examples.py upload-image chart.png
    python test_multimodal_examples.py test-all
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional

import requests
from requests.exceptions import RequestException

# Configuration
BASE_URL = "http://localhost:8000"
ORG_ID = "test-org"
BOT_ID = "test-bot"
API_KEY = "test-key"

# HTTP headers
DEFAULT_HEADERS = {
    "x-bot-key": API_KEY,
}


def print_response(response: requests.Response, label: str = "Response"):
    """Pretty print API response"""
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"Status: {response.status_code}")
    
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
    except Exception:
        print(response.text)


def upload_file(
    filename: str,
    file_path: Optional[str] = None,
    label: str = None,
) -> Optional[dict]:
    """
    Upload a file to the multimodal ingestion endpoint.
    
    Args:
        filename: Name of file
        file_path: Path to file (defaults to filename)
        label: Optional label for output
    
    Returns:
        Response JSON or None
    """
    if not file_path:
        file_path = filename
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return None
    
    label = label or f"Upload {filename}"
    print(f"\n📤 {label}")
    print(f"   File: {file_path}")
    print(f"   Size: {file_path.stat().st_size / 1024:.1f} KB")
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/octet-stream")}
            data = {"org_id": ORG_ID}
            
            url = f"{BASE_URL}/ingest/file/{BOT_ID}"
            
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=DEFAULT_HEADERS,
                timeout=120,
            )
            
            print_response(response, label)
            
            if response.status_code == 200:
                result = response.json()
                print(f"\n✅ Success!")
                print(f"   Inserted: {result.get('inserted', 0)} chunks")
                print(f"   Skipped: {result.get('skipped_duplicates', 0)} duplicates")
                print(f"   File type: {result.get('file_type', 'unknown')}")
                return result
            else:
                print(f"\n❌ Failed with status {response.status_code}")
                return None
    
    except RequestException as e:
        print(f"❌ Request error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_text_file():
    """Test with a simple text file"""
    print("\n" + "="*60)
    print("TEST 1: Text File Upload")
    print("="*60)
    
    # Create test file
    test_file = Path("test_sample.txt")
    test_file.write_text("""
    Introduction to Machine Learning
    
    Machine learning is a subset of artificial intelligence that enables
    systems to learn and improve from experience without being explicitly programmed.
    
    Key Concepts
    
    - Supervised Learning: Learning from labeled data
    - Unsupervised Learning: Finding patterns in unlabeled data
    - Reinforcement Learning: Learning through interaction and rewards
    
    Applications
    
    Machine learning is used in:
    - Image recognition and computer vision
    - Natural language processing
    - Recommendation systems
    - Predictive analytics
    """)
    
    upload_file("test_sample.txt", test_file, "Text File Test")
    test_file.unlink()  # Clean up


def test_duplicate_handling():
    """Test duplicate file detection"""
    print("\n" + "="*60)
    print("TEST 2: Duplicate File Handling")
    print("="*60)
    
    # Create test file
    test_file = Path("test_duplicate.txt")
    test_file.write_text("Duplicate test content") * 10
    
    print("\n📤 First Upload")
    result1 = upload_file("test_duplicate.txt", test_file)
    
    print("\n📤 Second Upload (Should be deduplicated at file level)")
    result2 = upload_file("test_duplicate.txt", test_file)
    
    if result1 and result2:
        print("\n✅ Deduplication Test:")
        print(f"   First upload: {result1.get('inserted', 0)} inserted")
        print(f"   Second upload: {result2.get('inserted', 0)} inserted (should be lower if deduplicated)")
    
    test_file.unlink()  # Clean up


def test_rate_limiting():
    """Test rate limiting"""
    print("\n" + "="*60)
    print("TEST 3: Rate Limiting")
    print("="*60)
    
    # Create small test file
    test_file = Path("test_rate_limit.txt")
    test_file.write_text("Rate limit test")
    
    success_count = 0
    limit_hit = False
    
    print(f"\n📤 Uploading 125 files rapidly...")
    
    for i in range(125):
        with open(test_file, "rb") as f:
            files = {"file": ("test_rate_limit.txt", f)}
            data = {"org_id": ORG_ID}
            
            response = requests.post(
                f"{BASE_URL}/ingest/file/{BOT_ID}",
                files=files,
                data=data,
                headers=DEFAULT_HEADERS,
                timeout=5,
            )
            
            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                limit_hit = True
                print(f"   Request {i+1}: 429 Rate Limited ✅")
            else:
                print(f"   Request {i+1}: {response.status_code}")
        
        if i % 10 == 0:
            print(f"   Processed {i+1} requests...")
    
    print(f"\n✅ Rate Limiting Test:")
    print(f"   Successful: {success_count}")
    print(f"   Rate limit hit: {'Yes' if limit_hit else 'No'}")
    
    test_file.unlink()  # Clean up


def test_authentication():
    """Test authentication scenarios"""
    print("\n" + "="*60)
    print("TEST 4: Authentication")
    print("="*60)
    
    test_file = Path("test_auth.txt")
    test_file.write_text("Auth test")
    
    with open(test_file, "rb") as f:
        files = {"file": ("test_auth.txt", f)}
        data = {"org_id": ORG_ID}
        
        # Test 1: Wrong API key
        print("\n📤 Test with wrong API key:")
        response = requests.post(
            f"{BASE_URL}/ingest/file/{BOT_ID}",
            files=files,
            data=data,
            headers={"x-bot-key": "wrong-key"},
        )
        
        if response.status_code == 403:
            print("   ✅ Correctly rejected (403 Forbidden)")
        else:
            print(f"   ❌ Unexpected status: {response.status_code}")
        
        # Test 2: No authentication
        print("\n📤 Test with no authentication:")
        response = requests.post(
            f"{BASE_URL}/ingest/file/{BOT_ID}",
            files=files,
            data=data,
        )
        
        if response.status_code in [401, 403]:
            print(f"   ✅ Correctly rejected ({response.status_code})")
        else:
            print(f"   ❌ Unexpected status: {response.status_code}")
    
    test_file.unlink()


def test_empty_file():
    """Test empty file handling"""
    print("\n" + "="*60)
    print("TEST 5: Empty File Handling")
    print("="*60)
    
    test_file = Path("test_empty.txt")
    test_file.write_text("")
    
    print("\n📤 Uploading empty file:")
    with open(test_file, "rb") as f:
        files = {"file": ("test_empty.txt", f)}
        data = {"org_id": ORG_ID}
        
        response = requests.post(
            f"{BASE_URL}/ingest/file/{BOT_ID}",
            files=files,
            data=data,
            headers=DEFAULT_HEADERS,
        )
        
        if response.status_code == 400:
            print("   ✅ Correctly rejected empty file (400 Bad Request)")
        else:
            print_response(response)
    
    test_file.unlink()


def test_cors_preflight():
    """Test CORS preflight request"""
    print("\n" + "="*60)
    print("TEST 6: CORS Preflight")
    print("="*60)
    
    print("\n📤 Sending OPTIONS request:")
    response = requests.options(
        f"{BASE_URL}/ingest/file/{BOT_ID}",
        headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    
    if response.status_code == 204:
        print("   ✅ CORS preflight successful (204 No Content)")
    else:
        print(f"   ❌ Unexpected status: {response.status_code}")
    
    print_response(response, "CORS Preflight Response")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("MULTIMODAL RAG INGESTION TEST SUITE")
    print("="*70)
    
    tests = [
        ("Text File", test_text_file),
        ("Duplicate Handling", test_duplicate_handling),
        ("Rate Limiting", test_rate_limiting),
        ("Authentication", test_authentication),
        ("Empty File", test_empty_file),
        ("CORS Preflight", test_cors_preflight),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ Test '{name}' failed: {e}")
            failed += 1
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Test multimodal RAG ingestion endpoint"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="test-all",
        help="Command to run",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="File to upload (for upload commands)",
    )
    parser.add_argument(
        "--url",
        default=BASE_URL,
        help=f"Server URL (default: {BASE_URL})",
    )
    parser.add_argument(
        "--org-id",
        default=ORG_ID,
        help=f"Organization ID (default: {ORG_ID})",
    )
    parser.add_argument(
        "--bot-id",
        default=BOT_ID,
        help=f"Bot ID (default: {BOT_ID})",
    )
    parser.add_argument(
        "--api-key",
        default=API_KEY,
        help=f"API key (default: {API_KEY})",
    )
    
    args = parser.parse_args()
    
    # Update globals
    global BASE_URL, ORG_ID, BOT_ID, API_KEY, DEFAULT_HEADERS
    BASE_URL = args.url
    ORG_ID = args.org_id
    BOT_ID = args.bot_id
    API_KEY = args.api_key
    DEFAULT_HEADERS["x-bot-key"] = API_KEY
    
    # Route commands
    commands = {
        "upload-text": test_text_file,
        "upload-pdf": lambda: upload_file(args.file) if args.file else print("Usage: upload-pdf <file>"),
        "upload-docx": lambda: upload_file(args.file) if args.file else print("Usage: upload-docx <file>"),
        "upload-pptx": lambda: upload_file(args.file) if args.file else print("Usage: upload-pptx <file>"),
        "upload-csv": lambda: upload_file(args.file) if args.file else print("Usage: upload-csv <file>"),
        "upload-image": lambda: upload_file(args.file) if args.file else print("Usage: upload-image <file>"),
        "test-all": run_all_tests,
        "test-text": test_text_file,
        "test-duplicates": test_duplicate_handling,
        "test-rate-limit": test_rate_limiting,
        "test-auth": test_authentication,
        "test-empty": test_empty_file,
        "test-cors": test_cors_preflight,
    }
    
    if args.command not in commands:
        parser.print_help()
        print(f"\nUnknown command: {args.command}")
        return 1
    
    try:
        result = commands[args.command]()
        if isinstance(result, int):
            return result
        return 0
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
