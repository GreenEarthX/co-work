"""Multi-currency CFADS: each revenue/opex stream carries its own currency and its
contract-specified fx_rate to the base currency (routes_model + CFADSCalculator)."""
import asyncio

from pf_engine.core.cfads import CFADSCalculator
from pf_engine.api.routes_model import (
    CurrencyStream,
    MultiCurrencyCFADSRequest,
    calculate_cfads_multi_currency,
)


def test_calculate_multi_currency_converts_each_stream_at_its_rate():
    r = CFADSCalculator.calculate_multi_currency(
        revenue_streams=[{"label": "eur", "amount": 100_000_000, "currency": "EUR", "fx_rate": 1.0},
                         {"label": "usd", "amount": 50_000_000, "currency": "USD", "fx_rate": 0.92}],
        opex_streams=[{"label": "power", "amount": 40_000_000, "currency": "EUR", "fx_rate": 1.0}],
        base_currency="EUR", maintenance_capex=5_000_000)
    assert r["total_revenue_base"] == 146_000_000.0        # 100M + 50M*0.92
    assert r["cfads"] == 79_790_000.0
    assert set(r["fx_exposure"]["currencies"]) == {"EUR", "USD"}
    usd = [s for s in r["revenue_streams"] if s["currency"] == "USD"][0]
    assert usd["amount_base"] == 46_000_000.0


def test_route_returns_success_and_per_stream_detail():
    req = MultiCurrencyCFADSRequest(
        revenue_streams=[CurrencyStream(label="usd", amount=50_000_000, currency="USD", fx_rate=0.92)],
        opex_streams=[], base_currency="EUR")
    out = asyncio.run(calculate_cfads_multi_currency(req))
    assert out["success"] is True
    assert out["cfads"]["total_revenue_base"] == 46_000_000.0
