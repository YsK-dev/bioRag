import urllib.request
import json
import time

url = "http://localhost:8001/api/query"
data = json.dumps({"query": "What are the main symptoms of RARS1?"}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

print(f"Sending request to {url}...")
start = time.time()
try:
    with urllib.request.urlopen(req, timeout=300) as response:
        result = response.read().decode('utf-8')
        print(f"\n✅ Success ({(time.time()-start):.2f}s):\n{result}")
except Exception as e:
    print(f"\n❌ Error ({(time.time()-start):.2f}s): {e}")
