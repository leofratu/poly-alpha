import requests
import json
from tradfi import get_tradfi_implied_probability, extract_financial_target
from datetime import datetime, timezone

events = requests.get("https://gamma-api.polymarket.com/events?active=true&closed=false&limit=1000").json()
for e in events:
    tags = e.get("tags", [])
    if any(t.get("label") in ("Economy", "Finance") for t in tags):
        for m in e.get("markets", []):
            q = m.get("question", e.get("title", ""))
            parsed = extract_financial_target(q)
            if parsed:
                print(q, "->", parsed)
                end = datetime.strptime(m["endDate"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                prob = get_tradfi_implied_probability(q, end)
                print("Prob:", prob)
