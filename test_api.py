"""
Test script for the Markdown to PDF API
Run with: python test_api.py
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_health():
    """Test the health endpoint"""
    print("🧪 Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/api/health")
    
    if response.status_code == 200:
        print("✅ Health check passed!")
        print(f"   Response: {response.json()}")
    else:
        print(f"❌ Health check failed: {response.status_code}")
    
    return response.status_code == 200

def test_info():
    """Test the info endpoint"""
    print("\n🧪 Testing info endpoint...")
    response = requests.get(f"{BASE_URL}/api/info")
    
    if response.status_code == 200:
        print("✅ Info endpoint passed!")
        data = response.json()
        print(f"   Name: {data.get('name')}")
        print(f"   Version: {data.get('version')}")
    else:
        print(f"❌ Info endpoint failed: {response.status_code}")
    
    return response.status_code == 200

def test_convert():
    """Test the convert endpoint"""
    print("\n🧪 Testing convert endpoint...")
    
    markdown_content = """# Test Document

## Introduction
This is a **test** document with various markdown features.

### Features
- Lists
- **Bold** text
- *Italic* text
- `code blocks`

### Code Example
```python
def hello():
    print("Hello, World!")
```

> This is a blockquote

---

## Conclusion
End of test document.
"""
    
    payload = {
        "markdown": markdown_content,
        "filename": "test_output.pdf"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/convert",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        print("✅ Convert endpoint passed!")
        
        # Save the PDF
        with open("test_output.pdf", "wb") as f:
            f.write(response.content)
        
        print(f"   PDF saved to: test_output.pdf")
        print(f"   PDF size: {len(response.content)} bytes")
    else:
        print(f"❌ Convert endpoint failed: {response.status_code}")
        try:
            print(f"   Error: {response.json()}")
        except:
            print(f"   Error: {response.text}")
    
    return response.status_code == 200

def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🚀 Starting API Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("Info Endpoint", test_info()))
    results.append(("Convert Endpoint", test_convert()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The API is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the output above.")

if __name__ == "__main__":
    try:
        run_all_tests()
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to the API server.")
        print("   Make sure the backend is running:")
        print("   python -m uvicorn api.index:app --reload --port 8000")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
