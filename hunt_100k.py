import json
import urllib.request

url = "https://gamma-api.polymarket.com/events?closed=false&active=true&limit=1000"
req = urllib.request.Request(url, headers={"User-Agent": "PolyArbScanner/2.0"})
with urllib.request.urlopen(req) as resp:
    events = json.loads(resp.read().decode())

for event in events:
    for m in event.get("markets", []):
        q = m.get("question", "")
        if "Will Bitcoin hit" in q and "$100k" in q:
            tokens = json.loads(m.get("outcomePrices", "[]"))
            if tokens:
                print(f"{q}: Yes Price = {tokens[0]}")
