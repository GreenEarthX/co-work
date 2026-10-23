"""
Trading book revision M1 — the pure core: conventions, validation, canonical hash, pricing.

Spec tests T01–T08 (and T11's rule) in the form M1 can prove without the API:
every rule V01–V13 has a failing and a passing case; amounts are exact Decimals;
the hash is stable and moves with any economic field; the side convention is
symmetric. The PostgreSQL side (frozen-terms trigger, policies) is
test_trading_terms_pg.py.
"""
from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal as D

import pytest

from app.trading_book import canonical, conventions as cv, pricing
from app.trading_book.terms import TermsIn
from app.trading_book.validation import Context, IndexInfo, validate

PRD, OFT, IDX = "00000000-0000-4000-8000-0000000000a1", "00000000-0000-4000-8000-0000000000b1", \
    "00000000-0000-4000-8000-0000000000c1"


def physical(parties: bool = True, payment: dict | None = None) -> dict:
    """The spec §6 example: 1,000 t e-methanol, RFNBO, delivered basis."""
    pay = payment or {"flow_type": "fixed_cash", "unit_price": "900", "quantity_basis": "delivered",
                      "quantity_source_flow": "1.1"}
    return {
        "settlement": "physical", "commodity": "EMEOH", "quality_spec": {"certification": "RFNBO"},
        "currency": "EUR",
        "legs": [
            {"seq": 1, "leg_role": "product", **({"payer": PRD, "receiver": OFT} if parties else {}),
             "flows": [{"seq": 1, "flow_type": "physical", "period_start": "2027-01-01",
                        "period_end": "2027-01-31", "settle_date": "2027-01-31", "quantity": "1000",
                        "unit": "t", "tolerance_min_pct": "-5", "tolerance_max_pct": "5"}]},
            {"seq": 2, "leg_role": "payment", **({"payer": OFT, "receiver": PRD} if parties else {}),
             "flows": [{"seq": 1, "period_start": "2027-01-01", "period_end": "2027-01-31",
                        "settle_date": "2027-02-28", "quantity": "1000", "unit": "t", **pay}]},
        ],
    }


def cash(parties: bool = True) -> dict:
    return {
        "settlement": "cash_net", "commodity": "EMEOH", "currency": "EUR",
        "legs": [
            {"seq": 1, "leg_role": "fixed", **({"payer": OFT, "receiver": PRD} if parties else {}),
             "flows": [{"seq": 1, "flow_type": "fixed_cash", "period_start": "2027-01-01",
                        "period_end": "2027-01-31", "settle_date": "2027-02-05", "quantity": "1000",
                        "unit": "t", "is_notional": True, "unit_price": "900"}]},
            {"seq": 2, "leg_role": "floating", **({"payer": PRD, "receiver": OFT} if parties else {}),
             "flows": [{"seq": 1, "flow_type": "float_cash", "period_start": "2027-01-01",
                        "period_end": "2027-01-31", "settle_date": "2027-02-05", "quantity": "1000",
                        "unit": "t", "is_notional": True, "index": IDX, "fixing_method": "average",
                        "fixing_start": "2027-01-01", "fixing_end": "2027-01-31"}]},
        ],
    }


CTX = Context(indices={IDX: IndexInfo("EUR", "t")})


def check(payload: dict, kind: str = "contract", ctx: Context = CTX) -> list[str]:
    return validate(TermsIn.model_validate(payload), kind, ctx)


def with_float_payment(**over) -> dict:
    return physical(payment={"flow_type": "float_cash", "index": IDX, "fixing_method": "average",
                             "fixing_start": "2027-01-01", "fixing_end": "2027-01-31",
                             "quantity_basis": "delivered", "quantity_source_flow": "1.1", **over})


# ── T01: every rule fails on a broken case and passes on the base case ──────

def _drop_leg(p):
    p["legs"].pop(); return p


def _two_products(p):
    p["legs"][1]["leg_role"] = "product"; return p


def _cash_in_product(p):
    p["legs"][0]["flows"][0].update(flow_type="fixed_cash", unit_price="1"); return p


def _cash_not_notional(p):
    p["legs"][0]["flows"][0]["is_notional"] = False; return p


def _missing_payer(p):
    p["legs"][0].pop("payer"); return p


def _same_direction(p):
    p["legs"][1].update(payer=PRD, receiver=OFT); return p


def _cash_same_direction(p):
    p["legs"][1].update(payer=OFT, receiver=PRD); return p


def _other_currency(p):
    p["legs"][1]["flows"][0]["currency"] = "USD"; return p


def _no_source(p):
    p["legs"][1]["flows"][0].pop("quantity_source_flow"); return p


def _unknown_index(_):
    return with_float_payment(index="00000000-0000-4000-8000-0000000000ff")


def _reversed_period(p):
    p["legs"][0]["flows"][0].update(period_start="2027-02-01"); return p


CASES = [  # rule, how to break the base, base builder, kind, context
    ("V01", _drop_leg, physical, "contract", CTX),
    ("V02", _two_products, physical, "contract", CTX),
    ("V03", _cash_in_product, physical, "contract", CTX),
    ("V04", _cash_not_notional, cash, "contract", Context(CTX.indices, allow_cash_settled=True)),
    ("V06", _missing_payer, physical, "contract", CTX),
    ("V07", _same_direction, physical, "contract", CTX),
    ("V08", _cash_same_direction, cash, "contract", Context(CTX.indices, allow_cash_settled=True)),
    ("V09", _other_currency, physical, "contract", CTX),
    ("V10", _no_source, physical, "contract", CTX),
    ("V11", _unknown_index, physical, "contract", CTX),
    ("V12", _reversed_period, physical, "contract", CTX),
]


@pytest.mark.parametrize("rule, breaks, base, kind, ctx", CASES, ids=[c[0] for c in CASES])
def test_t01_each_rule_passes_the_base_and_fails_the_break(rule, breaks, base, kind, ctx):
    assert check(base(), kind, ctx) == []
    assert rule in check(breaks(base()), kind, ctx)


def test_t01_v05_cash_settlement_needs_the_flag():
    assert check(cash()) == ["V05"]
    assert check(cash(), ctx=Context(CTX.indices, allow_cash_settled=True)) == []      # T02


def test_t01_v06_order_terms_name_no_party():
    assert check(physical(parties=False), "order") == []
    assert "V06" in check(physical(parties=True), "order")


def test_t01_v11_a_convertible_or_mismatched_index_is_refused():
    assert check(with_float_payment()) == []
    assert "V11" in check(with_float_payment(), ctx=Context({IDX: IndexInfo("USD", "t")}))
    assert "V11" in check(with_float_payment(), ctx=Context({IDX: IndexInfo("EUR", "t", convertible=True)}))


def test_t01_v13_restricted_pair_in_either_direction():                         # T09's rule
    restricted = Context(CTX.indices, restricted_pairs={frozenset({PRD, OFT})})
    assert check(physical(), ctx=restricted) == ["V13"]
    assert check(physical()) == []


# ── T03 / T04 / T05: exact amounts ──────────────────────────────────────────

def test_t03_fixed_is_exact():
    assert pricing.fixed_amount(D("1000"), D("900")) == D("900000.00")


def test_t04_delivered_basis():
    q, projected = pricing.payment_quantity(D("1000"), "delivered", D("970"))
    assert (pricing.fixed_amount(q, D("900")), projected) == (D("873000.00"), False)
    q, projected = pricing.payment_quantity(D("1000"), "delivered", None)
    assert (pricing.fixed_amount(q, D("900")), projected) == (D("900000.00"), True)


@pytest.mark.parametrize("fix, expected", [
    (D("50"), D("80.00")),      # 50 + 15.50 = 65.50, below the floor
    (D("100"), D("115.50")),    # inside the collar
    (D("300"), D("250.00")),    # 315.50, above the cap
])
def test_t05_float_collar_clamps(fix, expected):
    # The Rotterdam fixture's collar: floor 80, cap 250, spread 15.50 — on 1 unit.
    assert pricing.float_amount(D("1"), fix, spread=D("15.50"), floor=D("80"), cap=D("250")) == expected
    assert pricing.float_amount(D("2"), fix, spread=D("15.50"), floor=D("80"), cap=D("250")) == 2 * expected


def test_fixings():
    vals = [D("100"), D("110"), D("120")]
    assert (pricing.fixing(vals, "first"), pricing.fixing(vals, "last"), pricing.fixing(vals, "average")) \
        == (D("100"), D("120"), D("110"))


# ── T06 / T07: the side convention ──────────────────────────────────────────

def test_t07_accepting_a_sell_order_and_a_buy_order():
    buyer, seller = cv.parties_at_acceptance(cv.Side.SELL, order_owner="owner", acceptor="taker")
    assert cv.resolve(cv.LegRole.PRODUCT, buyer, seller) == ("owner", "taker")   # owner delivers
    assert cv.resolve(cv.LegRole.PAYMENT, buyer, seller) == ("taker", "owner")   # taker pays
    buyer, seller = cv.parties_at_acceptance(cv.Side.BUY, order_owner="owner", acceptor="taker")
    assert cv.resolve(cv.LegRole.PRODUCT, buyer, seller) == ("taker", "owner")
    assert cv.resolve(cv.LegRole.PAYMENT, buyer, seller) == ("owner", "taker")


def test_t06_perspective_symmetry():
    amount = pricing.fixed_amount(D("1000"), D("900"))
    for role in cv.LegRole:
        payer, receiver = cv.resolve(role, "B", "S")
        signed = {p: cv.direction(p, payer, receiver) * amount for p in ("B", "S")}
        assert signed["B"] == -signed["S"] and sum(signed.values()) == 0


# ── T08: the hash ───────────────────────────────────────────────────────────

def test_t08_hash_is_stable_and_moves_with_economics():
    terms = TermsIn.model_validate(physical())
    first = canonical.terms_hash(terms)
    reparsed = TermsIn.model_validate_json(TermsIn.model_validate(physical()).model_dump_json())
    assert canonical.terms_hash(reparsed) == first
    # leg and flow order in the payload do not matter
    shuffled = physical()
    shuffled["legs"].reverse()
    assert canonical.terms_hash(TermsIn.model_validate(shuffled)) == first
    # trailing zeros do not matter; the economics do
    assert canonical.terms_hash(TermsIn.model_validate(
        physical(payment={"flow_type": "fixed_cash", "unit_price": "900.000", "quantity_basis": "delivered",
                          "quantity_source_flow": "1.1"}))) == first
    for path, value in ((("legs", 1, "flows", 0, "unit_price"), "900.01"),
                        (("legs", 0, "flows", 0, "quantity"), "1001"),
                        (("legs", 0, "payer"), "00000000-0000-4000-8000-0000000000d1"),
                        (("quality_spec", "certification"), "GoO"),
                        (("legs", 1, "flows", 0, "settle_date"), "2027-03-01")):
        p = copy.deepcopy(physical())
        node = p
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
        assert canonical.terms_hash(TermsIn.model_validate(p)) != first, path


def test_t08_canonical_form_matches_the_spec_example():
    c = canonical.canonical_dict(TermsIn.model_validate(physical()))
    product = c["legs"][0]
    assert product["payer"] == f"cp:{PRD}" and product["flows"][0]["quantity"] == "1000.000000"
    assert product["flows"][0]["tolerance_min_pct"] == "-5.0000"
    pay = c["legs"][1]["flows"][0]
    assert pay["unit_price"] == "900.00000000" and pay["spread"] == "0.00000000"
    assert pay["quantity_source_flow"] == "1.1" and "index_multiplier" not in pay
    assert b" " not in canonical.canonical_bytes(TermsIn.model_validate(physical())).replace(b"e-", b"")
