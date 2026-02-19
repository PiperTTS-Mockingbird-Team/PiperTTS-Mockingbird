"""
Quick test to verify the updated single-pass citation code works correctly.
"""
from ddgsearch import get_combined_response

# Test query
query = "Where was Donald Trump born?"

print("Testing updated single-pass citation code...")
print(f"Query: {query}\n")

try:
    answer = get_combined_response(query, model='qwen3:1.7b')
    print(f"Answer: {answer}\n")
    
    # Check if citations are present
    import re
    citations = re.findall(r'\[(\d+)\]', answer)
    
    if citations:
        print(f"✓ SUCCESS: Citations found: {citations}")
        print("Single-pass citation generation is working!")
    else:
        print("⚠ WARNING: No citations found in answer")
        print("This might be okay if no search was performed")
        
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
