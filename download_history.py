import json
import urllib.request
import sqlite3
import concurrent.futures
from rich.console import Console

console = Console()
DB_FILE = "/home/leo_dwelon_com/.openclaw/workspace/poly-alpha/historical_markets.sqlite"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS markets (
            id TEXT PRIMARY KEY,
            question TEXT,
            condition_id TEXT,
            slug TEXT,
            end_date TEXT,
            created_at TEXT,
            closed_time TEXT,
            volume REAL,
            liquidity REAL,
            outcome TEXT,
            yes_price REAL,
            no_price REAL,
            tags TEXT,
            is_crypto INTEGER,
            is_sports INTEGER,
            is_politics INTEGER
        )
    ''')
    conn.commit()
    return conn

def fetch_batch(offset, limit=1000):
    url = f"https://gamma-api.polymarket.com/events?closed=true&limit={limit}&offset={offset}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception as e:
        return None

def process_and_save():
    console.print("[bold cyan]Spinning up 20 workers to rip the entire Polymarket history database...[/bold cyan]")
    conn = init_db()
    
    offsets = list(range(0, 300000, 1000))
    total_saved = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_offset = {executor.submit(fetch_batch, off): off for off in offsets}
        
        for future in concurrent.futures.as_completed(future_to_offset):
            events = future.result()
            if not events:
                continue
                
            batch_markets = []
            for event in events:
                tags = [t.get("label", "").lower() for t in event.get("tags", [])]
                is_crypto = 1 if any("crypto" in t or "bitcoin" in t or "ethereum" in t for t in tags) else 0
                is_sports = 1 if any("sports" in t or "nfl" in t or "nba" in t or "ncaa" in t for t in tags) else 0
                is_politics = 1 if any("politics" in t or "election" in t for t in tags) else 0
                tags_str = ",".join(tags)
                
                for m in event.get("markets", []):
                    try:
                        tokens = json.loads(m.get("outcomePrices", "[]"))
                        yes_price = float(tokens[0]) if len(tokens) > 0 else 0.0
                        no_price = 1.0 - yes_price
                    except Exception:
                        yes_price, no_price = 0.0, 0.0
                        
                    batch_markets.append((
                        m.get("id"),
                        m.get("question"),
                        m.get("conditionId"),
                        m.get("slug"),
                        m.get("endDate"),
                        m.get("createdAt"),
                        m.get("closedTime"),
                        float(m.get("volume", 0)),
                        float(m.get("liquidity", 0)),
                        m.get("outcome"),
                        yes_price,
                        no_price,
                        tags_str,
                        is_crypto,
                        is_sports,
                        is_politics
                    ))
            
            if batch_markets:
                c = conn.cursor()
                c.executemany('''
                    INSERT OR IGNORE INTO markets 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', batch_markets)
                conn.commit()
                total_saved += len(batch_markets)
                console.print(f"Ingested {len(batch_markets)} markets... (Total in DB: {total_saved})")

    console.print(f"\n[bold green]Download complete![/bold green] Successfully created a local SQLite database of {total_saved} historical markets.")

if __name__ == "__main__":
    process_and_save()
