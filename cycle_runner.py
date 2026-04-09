from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def export_portfolio(db_path: Path, out_dir: Path, preset: str) -> tuple[Path, Path]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    wallet = cur.execute("SELECT free_capital FROM wallet WHERE id=1").fetchone()
    positions = cur.execute(
        """
        SELECT id, market_id, question, entry_time, entry_no_price, investment, shares, status, payout, pnl
        FROM positions
        ORDER BY entry_time DESC
        """
    ).fetchall()
    conn.close()

    open_positions = [dict(row) for row in positions if row["status"] == "OPEN"]
    closed_positions = [dict(row) for row in positions if row["status"] == "CLOSED"]
    for row in open_positions + closed_positions:
        row["entry_iso"] = datetime.fromtimestamp(row["entry_time"], tz=timezone.utc).isoformat()

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "preset": preset,
        "total_trades": len(positions),
        "trade_count": len(positions),
        "open_trades": len(open_positions),
        "open_trade_count": len(open_positions),
        "closed_trades": len(closed_positions),
        "closed_trade_count": len(closed_positions),
        "free_capital": wallet["free_capital"] if wallet else 0.0,
        "locked_capital": sum(row["investment"] for row in open_positions),
        "realized_pnl": sum((row["pnl"] or 0.0) for row in closed_positions),
        "positions": open_positions + closed_positions,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "portfolio.json"
    csv_path = out_dir / "portfolio.csv"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "market_id",
                "question",
                "entry_iso",
                "entry_no_price",
                "investment",
                "shares",
                "status",
                "payout",
                "pnl",
            ],
        )
        writer.writeheader()
        for row in summary["positions"]:
            writer.writerow({k: row.get(k) for k in writer.fieldnames})

    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one fresh clean-strategy paper-trading cycle and export the portfolio.")
    parser.add_argument("--db", default="data/paper_cycles/live_cycle/paper_wallet.sqlite")
    parser.add_argument(
        "--preset",
        default="strict",
        choices=["strict", "paper_reset", "balanced", "throughput", "expansion", "quality_expansion", "acceleration"],
    )
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset and db_path.exists():
        db_path.unlink()

    os.environ["POLY_ALPHA_DB"] = str(db_path)
    os.environ["POLY_ALPHA_PRESET"] = args.preset
    import paper_engine  # imported after env so DB_FILE picks up the requested path

    if not db_path.exists():
        paper_engine.init_db()

    paper_engine.settle_trades()
    paper_engine.deploy_trades()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("data/paper_cycles") / timestamp
    json_path, csv_path = export_portfolio(db_path, out_dir, args.preset)
    latest_dir = Path("data/paper_cycles/latest")
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_json, latest_csv = export_portfolio(db_path, latest_dir, args.preset)
    print(json.dumps({
        "db_path": str(db_path),
        "preset": args.preset,
        "export_json": str(json_path),
        "export_csv": str(csv_path),
        "latest_json": str(latest_json),
        "latest_csv": str(latest_csv),
    }, indent=2))


if __name__ == "__main__":
    main()
