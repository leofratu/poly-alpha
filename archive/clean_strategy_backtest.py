from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import heappop, heappush
from pathlib import Path

from perfect_strategy_real_backtest import (
    _safe_json_loads,
    _to_utc_ts,
    fetch_closed_markets,
    fetch_price_history,
)
from strategy_core import candidate_from_market, clean_late_no_config


@dataclass
class Signal:
    market_id: str
    question: str
    category: str
    market_type: str
    entry_ts: int
    exit_ts: int
    entry_no_price: float
    won: bool


@dataclass
class Position:
    signal: Signal
    stake: float
    shares: float


def find_signal(market: dict, fidelity: int):
    outcomes = _safe_json_loads(market.get("outcomes", [])) or []
    token_ids = _safe_json_loads(market.get("clobTokenIds", [])) or []
    if len(outcomes) != 2 or len(token_ids) < 2:
        return None
    outcomes_norm = [str(o).strip().lower() for o in outcomes]
    if set(outcomes_norm) != {"yes", "no"}:
        return None

    yes_index = outcomes_norm.index("yes")
    yes_token = str(token_ids[yes_index])
    history = fetch_price_history(yes_token, fidelity)
    if not history:
        return None

    cfg = clean_late_no_config()
    created_ts = _to_utc_ts(market.get("createdAt"))
    end_ts = _to_utc_ts(market.get("endDate"))
    close_ts = _to_utc_ts(market.get("closedTime")) or end_ts
    if not created_ts or not end_ts or not close_ts:
        return None

    final_prices = _safe_json_loads(market.get("outcomePrices", [])) or []
    if len(final_prices) < 2:
        return None
    won = float(final_prices[1]) >= 0.999

    for ts, yes_price in history:
        point_time = datetime.fromtimestamp(ts, tz=timezone.utc)
        snap = dict(market)
        snap["outcomePrices"] = json.dumps([yes_price, 1.0 - yes_price])
        candidate, _ = candidate_from_market(snap, point_time, cfg)
        if candidate is None:
            continue
        return Signal(
            market_id=str(market.get("id", "")),
            question=market.get("question", ""),
            category=candidate["category"],
            market_type=candidate["market_type"],
            entry_ts=ts,
            exit_ts=close_ts,
            entry_no_price=candidate["no_price"],
            won=won,
        )
    return None


def replay(signals: list[Signal], bankroll: float, risk_pct: float, max_concurrent: int, deploy_cap: float):
    cash = bankroll
    open_heap: list[tuple[int, Position]] = []
    closed = []
    peak = bankroll
    max_dd = 0.0

    def settle_until(ts: int):
        nonlocal cash, peak, max_dd
        while open_heap and open_heap[0][0] <= ts:
            _, pos = heappop(open_heap)
            payout = pos.shares if pos.signal.won else 0.0
            pnl = payout - pos.stake
            cash += payout
            equity = cash + sum(p.stake for _, p in open_heap)
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
            closed.append((pos.signal, pos.stake, pnl))

    for signal in sorted(signals, key=lambda s: s.entry_ts):
        settle_until(signal.entry_ts)
        if len(open_heap) >= max_concurrent:
            continue
        deployed = sum(p.stake for _, p in open_heap)
        equity = cash + deployed
        allowed = equity * deploy_cap - deployed
        stake = min(equity * risk_pct, cash, allowed)
        if stake < 1.0:
            continue
        shares = stake / signal.entry_no_price
        cash -= stake
        heappush(open_heap, (signal.exit_ts, Position(signal=signal, stake=stake, shares=shares)))

    settle_until(10**18)
    final_equity = cash
    wins = sum(1 for _, _, pnl in closed if pnl > 0)
    return {
        "signals": len(signals),
        "fills": len(closed),
        "wins": wins,
        "win_rate": (wins / len(closed) * 100.0) if closed else 0.0,
        "final_bankroll": final_equity,
        "roi_pct": ((final_equity / bankroll) - 1.0) * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "sample_trades": [
            {
                "market_id": s.market_id,
                "question": s.question,
                "category": s.category,
                "market_type": s.market_type,
                "entry_no_price": s.entry_no_price,
                "stake": stake,
                "pnl": pnl,
            }
            for s, stake, pnl in closed[:20]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the clean late-expiry strategy on resolved markets.")
    parser.add_argument("--max-events", type=int, default=300)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument("--pause-s", type=float, default=0.05)
    parser.add_argument("--fidelity", type=int, default=1440)
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--risk-pct", type=float, default=0.025)
    parser.add_argument("--max-concurrent", type=int, default=25)
    parser.add_argument("--deploy-cap", type=float, default=0.60)
    parser.add_argument("--market-limit", type=int, default=50)
    parser.add_argument("--output", default="data/backtests/clean_strategy_backtest.json")
    args = parser.parse_args()

    markets = fetch_closed_markets(args.max_events, args.pause_s, args.start_offset)[: args.market_limit]
    signals = []
    for idx, market in enumerate(markets, start=1):
        try:
            signal = find_signal(market, args.fidelity)
        except Exception:
            signal = None
        if signal is not None:
            signals.append(signal)
        if idx % 10 == 0:
            print(f"processed {idx}/{len(markets)} markets, signals={len(signals)}", flush=True)

    result = replay(signals, args.bankroll, args.risk_pct, args.max_concurrent, args.deploy_cap)
    result["config"] = vars(args)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
