from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_contains_fibonacci_map_and_trade_log() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for expected in (
        'id="fib-content"',
        'id="fib-levels"',
        'id="fib-swing-high"',
        'id="fib-entry"',
        'id="fib-swing-low"',
        'id="trade-log-list"',
        'id="clear-trade-log"',
    ):
        assert expected in html


def test_dashboard_uses_shared_server_trade_log() -> None:
    javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "'/api/trade-log'" in javascript
    assert "'/api/trade-log/clear'" in javascript
    assert "localStorage" not in javascript
    assert "renderFibSetup" in javascript
