"""
Test script for the multi-source search integration.
Tests SearXNG, DuckDuckGo, and Bing fallback functionality.
"""
import sys
from multi_search import search_multi_source, search_searxng, search_duckduckgo, search_bing

def print_separator():
    print("\n" + "="*70 + "\n")

def test_individual_sources():
    """Test each search source individually."""
    print("🧪 TESTING INDIVIDUAL SEARCH SOURCES")
    print_separator()
    
    test_query = "artificial intelligence"
    
    # Test SearXNG
    print("1️⃣  Testing SearXNG...")
    print("-" * 70)
    results, error = search_searxng(test_query, max_results=2)
    if results:
        print(f"✅ SearXNG SUCCESS: Found {len(results)} results")
        for i, r in enumerate(results, 1):
            print(f"   [{i}] {r.get('title', 'No title')[:50]}")
    else:
        print(f"❌ SearXNG FAILED: {error}")
        print("   ℹ️  This is expected if SearXNG is not running")
    
    print_separator()
    
    # Test DuckDuckGo
    print("2️⃣  Testing DuckDuckGo...")
    print("-" * 70)
    results, error = search_duckduckgo(test_query, max_results=2)
    if results:
        print(f"✅ DuckDuckGo SUCCESS: Found {len(results)} results")
        for i, r in enumerate(results, 1):
            print(f"   [{i}] {r.get('title', 'No title')[:50]}")
    else:
        print(f"❌ DuckDuckGo FAILED: {error}")
    
    print_separator()
    
    # Test Bing
    print("3️⃣  Testing Bing Fallback...")
    print("-" * 70)
    results, error = search_bing(test_query, max_results=2)
    if results:
        print(f"✅ Bing SUCCESS: Found {len(results)} results")
        for i, r in enumerate(results, 1):
            print(f"   [{i}] {r.get('title', 'No title')[:50]}")
    else:
        print(f"❌ Bing FAILED: {error}")
    
    print_separator()

def test_multi_source():
    """Test the multi-source search with automatic fallback."""
    print("🔄 TESTING MULTI-SOURCE SEARCH WITH FALLBACK")
    print_separator()
    
    test_queries = [
        "Python programming",
        "latest technology news",
        "weather forecast"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"Query {i}: '{query}'")
        print("-" * 70)
        
        results, source, errors = search_multi_source(query, max_results=2)
        
        if results:
            print(f"✅ SUCCESS using: {source.upper()}")
            print(f"   Found {len(results)} results")
            if errors:
                print(f"   ⚠️  Errors from other sources: {errors}")
            
            # Show first result
            if results:
                r = results[0]
                print(f"\n   First Result:")
                print(f"   📰 Title: {r.get('title', 'No title')[:60]}")
                print(f"   🔗 URL: {r.get('href', 'No URL')[:60]}")
                snippet = r.get('body', 'No snippet')[:100]
                print(f"   📝 Snippet: {snippet}...")
        else:
            print(f"❌ ALL SOURCES FAILED")
            print(f"   Errors: {errors}")
        
        print()
    
    print_separator()

def test_integration():
    """Test that ddgsearch.py can import and use the new system."""
    print("🔗 TESTING INTEGRATION WITH DDGSEARCH.PY")
    print_separator()
    
    try:
        # This tests that ddgsearch.py can properly import from multi_search
        import ddgsearch
        print("✅ ddgsearch.py imports successfully")
        
        # Test the search_internet function
        results, error = ddgsearch.search_internet("test query")
        print(f"✅ search_internet() function works")
        print(f"   Got {len(results)} results, error: {error}")
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
    except Exception as e:
        print(f"⚠️  Exception during test: {e}")
    
    print_separator()

def main():
    print("\n" + "="*70)
    print("  POTATO-LOCAL-AI MULTI-SOURCE SEARCH TEST SUITE")
    print("="*70)
    print("\nThis will test:")
    print("  1. Each search source individually (SearXNG, DuckDuckGo, Bing)")
    print("  2. The multi-source fallback system")
    print("  3. Integration with ddgsearch.py")
    print("\nNote: SearXNG will only work if your server is running at http://127.0.0.1:8888")
    print("="*70)
    
    input("\nPress ENTER to start tests...")
    
    try:
        # Run all tests
        test_individual_sources()
        test_multi_source()
        test_integration()
        
        # Summary
        print("\n" + "="*70)
        print("  TEST SUMMARY")
        print("="*70)
        print("\n✅ All tests completed!")
        print("\nNext steps:")
        print("  1. If SearXNG failed, make sure it's running:")
        print("     Run: Start-SearXNG (Windows).bat")
        print("  2. If all sources work, you're ready to use Potato-Local-AI!")
        print("  3. Launch the GUI with: python gui_app.py")
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error during tests: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
