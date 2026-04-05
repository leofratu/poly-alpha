import requests
events = requests.get("https://gamma-api.polymarket.com/events?active=true&closed=false&limit=1000").json()
found = []
for e in events:
    tags = e.get("tags", [])
    if any(t.get("label") in ("Economy", "Finance", "Crypto") for t in tags):
        found.append(e.get("title", ""))
print(found[:10])
