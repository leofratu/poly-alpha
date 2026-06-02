from __future__ import annotations

from datetime import datetime, timedelta, timezone

from arbitrage import scan_opportunities
from tradfi import (
    get_risk_free_rate,
    calculate_implied_probability,
    extract_financial_target,
)


def test_get_risk_free_rate():
    for days in [90, 365, 3650]:
        rate = get_risk_free_rate(days)
        assert isinstance(rate, float)
        assert 0 <= rate <= 15


def test_calculate_implied_probability():
    prob = calculate_implied_probability(
        S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.2
    )
    assert 0.45 < prob < 0.60

    prob_itm = calculate_implied_probability(
        S=120.0, K=100.0, T_years=1.0, r=0.05, sigma=0.2
    )
    assert prob_itm > 0.80


def test_extract_financial_target():
    res = extract_financial_target("Will SPY close above 500?")
    assert res is not None
    assert res.ticker == "SPY"
    assert res.target_price == 500.0

    res2 = extract_financial_target("BTC to $100k?")
    assert res2 is not None
    assert res2.ticker == "BTC-USD"
    assert res2.target_price == 100000.0

    res3 = extract_financial_target("AAPL crashes below $150?")
    assert res3 is not None
    assert res3.ticker == "AAPL"
    assert res3.target_price == 150.0


def test_scan_opportunities(monkeypatch):
    monkeypatch.setattr("arbitrage.get_tradfi_implied_probability", lambda q, d: 0.30)

    end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    mock_events = [
        {
            "id": "1",
            "title": "Will SPY close above 500?",
            "markets": [
                {
                    "id": "m1",
                    "question": "Will SPY close above 500?",
                    "endDate": end_date,
                    "active": True,
                    "closed": False,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.8", "0.2"]',
                    "volumeNum": 1000.0,
                }
            ],
        }
    ]

    opportunities = scan_opportunities(mock_events, threshold=5.0)

    assert len(opportunities) == 1
    opp = opportunities[0]
    assert opp.id == "m1"
    assert opp.favorite == "Yes"
    assert opp.price == 0.8
    assert opp.poly_prob == 80.0
    assert opp.tradfi_prob == 30.0
    assert opp.spread == 50.0
