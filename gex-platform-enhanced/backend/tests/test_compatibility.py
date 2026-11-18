"""
Eligibility before ranking (discovery Phase 1, R7; report §6.1–6.2): core/compatibility.assess.

Each requirement gives Compatible, Incompatible (reason) or Needs evidence (what). One mandatory
Incompatible excludes a listing whatever its price (check 6); absence of a claim is never proof of
the opposite (Needs evidence, not Incompatible); a preferred requirement only ranks.
"""
from __future__ import annotations

from app.core import compatibility as cx

LISTING = {"id": "o1", "molecule": "e-Methanol", "volume_mtpd": 40, "price_eur_kg": 1.1, "delivery_start": "2028-01-01",
           "delivery_end": "2028-12-31", "offer_type": "firm", "incoterm": "FOB", "named_place": "Rotterdam",
           "certification_pathway": "RFNBO", "product": {
               "physical_form": "liquid",
               "carbon_intensity": {"value_gco2e_mj": 9.4, "method": "DA 2023/1185", "system_boundary": "WtW",
                                    "basis": "calculated"},
               "quality": [{"parameter": "purity_pct_mass", "value": 99.85, "unit": "% m/m", "basis": "declared"}],
               "certificates": [{"kind": "certificate", "scheme": "ISCC EU", "body": "TEST", "scope": "site",
                                 "covers": "covers the site", "status": "verified",
                                 "valid_from": "2026-01-01", "valid_until": "2030-12-31"},
                                {"kind": "certificate", "scheme": "CertifHy", "body": "TEST", "scope": "batch",
                                 "covers": "covers this quantity", "status": "asserted",
                                 "valid_from": "2026-01-01", "valid_until": "2030-12-31"}]}}
RFQ = {"id": "r1", "molecule": "e-Methanol", "volume_mtpd": 10, "max_price_eur_kg": 1.3, "delivery_start": "2028-01-01",
       "delivery_end": "2028-12-31"}


def _rfq(**req):
    return {**RFQ, "requirements": req}


def _with(**changes):
    out = {**LISTING, "product": {**LISTING["product"]}}
    for k, v in changes.items():
        (out["product"] if k in ("physical_form", "carbon_intensity", "quality", "certificates") else out)[k] = v
    return out


def _outcome(a, key):
    return cx.outcome_of(a, key)["outcome"]


def test_a_mandatory_mismatch_stays_incompatible_at_any_price():           # check 6
    cheap_dirty = _with(price_eur_kg=0.01, carbon_intensity={"value_gco2e_mj": 32, "basis": "measured"})
    req = _rfq(max_ci_gco2e_mj=28.2, mandatory=["max_ci_gco2e_mj"])
    bad, good = cx.assess(req, cheap_dirty), cx.assess(req, LISTING)
    assert bad["status"] == "incompatible" and not bad["eligible"]
    assert cx.blocking(bad) == ["CI 32 gCO2e/MJ exceeds your 28.2 limit."]
    assert good["status"] == "compatible"
    ranked = sorted([(bad, cheap_dirty), (good, LISTING)], key=lambda x: cx.rank_key(*x))
    assert ranked[0][1] is LISTING                                           # the dearer, compatible one first


def test_a_preferred_requirement_ranks_but_never_excludes():
    a = cx.assess(_rfq(max_ci_gco2e_mj=5), LISTING)                         # not mandatory
    assert _outcome(a, "max_ci_gco2e_mj") == "incompatible" and a["eligible"] and a["status"] == "compatible"


def test_no_claim_is_needs_evidence_never_incompatible():
    req = _rfq(max_ci_gco2e_mj=28.2, physical_form="liquid", quality_limits={"water_ppm_mass": {"max": 500}},
               mandatory=["max_ci_gco2e_mj", "physical_form", "quality_limits"])
    a = cx.assess(req, _with(carbon_intensity=None, physical_form=None))
    assert {k: _outcome(a, k) for k in ("max_ci_gco2e_mj", "physical_form", "quality_limits")} == {
        "max_ci_gco2e_mj": "needs_evidence", "physical_form": "needs_evidence", "quality_limits": "needs_evidence"}
    assert a["status"] == "needs_evidence" and a["eligible"]


def test_carbon_intensity_basis_below_the_buyers_minimum_needs_evidence():
    a = cx.assess(_rfq(max_ci_gco2e_mj=28.2, ci_min_basis="measured", mandatory=["max_ci_gco2e_mj"]), LISTING)
    assert _outcome(a, "max_ci_gco2e_mj") == "needs_evidence" and "calculated" in cx.outcome_of(a, "max_ci_gco2e_mj")["reason"]
    mint = _with(carbon_intensity={"value_gco2e_mj": 9.4, "basis": "declared_at_mint"})
    assert _outcome(cx.assess(_rfq(ci_min_basis="estimate"), mint), "ci_min_basis") == "needs_evidence"


def test_certificates_by_scheme_status_and_scope():
    site = cx.assess(_rfq(accepted_schemes=["ISCC EU"], min_evidence_state="verified"), LISTING)
    o = cx.outcome_of(site, "accepted_schemes")
    assert o["outcome"] == "compatible" and "not this quantity" in o["reason"]          # a site certificate says so
    claimed = cx.assess(_rfq(accepted_schemes=["CertifHy"], min_evidence_state="verified"), LISTING)
    assert _outcome(claimed, "accepted_schemes") == "needs_evidence"
    expired = _with(certificates=[{**LISTING["product"]["certificates"][0], "status": "expired"}])
    assert _outcome(cx.assess(_rfq(accepted_schemes=["ISCC EU"]), expired), "accepted_schemes") == "needs_evidence"
    assert _outcome(cx.assess(_rfq(accepted_schemes=["REDcert"]), LISTING), "accepted_schemes") == "needs_evidence"


def test_regimes_are_claims_with_their_evidence():
    assert _outcome(cx.assess(_rfq(regimes=["RFNBO"]), LISTING), "regimes") == "compatible"
    assert _outcome(cx.assess(_rfq(regimes=["RFNBO"], min_evidence_state="verified"), LISTING), "regimes") == "needs_evidence"
    assert _outcome(cx.assess(_rfq(regimes=["ISCC EU"], min_evidence_state="verified"), LISTING), "regimes") == "compatible"
    assert _outcome(cx.assess(_rfq(regimes=["45V"]), LISTING), "regimes") == "needs_evidence"


def test_specification_form_and_delivery_basis_mismatches_are_incompatible():
    a = cx.assess(_rfq(quality_limits={"purity_pct_mass": {"min": 99.9}}, physical_form="gas", incoterms=["CIF"]), LISTING)
    assert [_outcome(a, k) for k in ("quality_limits", "physical_form", "incoterms")] == ["incompatible"] * 3
    place = cx.assess(_rfq(incoterms=["FOB"], named_place="Antwerp"), LISTING)
    assert _outcome(place, "incoterms") == "incompatible" and "Antwerp" in cx.outcome_of(place, "incoterms")["reason"]
    assert _outcome(cx.assess(_rfq(incoterms=["FOB"], named_place="rotterdam"), LISTING), "incoterms") == "compatible"


def test_molecule_and_window_always_decide():
    a = cx.assess({**_rfq(), "delivery_start": "2029-01-01", "delivery_end": "2029-12-31"}, LISTING)
    assert _outcome(a, "window") == "incompatible" and not a["eligible"]
    assert not cx.assess({**_rfq(), "molecule": "NH3"}, LISTING)["eligible"]


def test_price_volume_and_indicative_only_rank():
    a = cx.assess({**_rfq(), "max_price_eur_kg": 1.0, "volume_mtpd": 50}, _with(offer_type="indicative"))
    assert {k: _outcome(a, k) for k in ("price", "volume", "offer_type")} == {
        "price": "incompatible", "volume": "incompatible", "offer_type": "needs_evidence"}
    assert a["eligible"] and a["status"] == "compatible"


def test_the_requirements_hash_is_stable():
    assert cx.requirements_sha256({"b": 1, "a": [1, 2]}) == cx.requirements_sha256({"a": [1, 2], "b": 1})


def test_a_certificate_must_cover_the_whole_delivery_window_not_just_today():
    iscc = LISTING["product"]["certificates"][0]
    req = _rfq(accepted_schemes=["ISCC EU"], mandatory=["accepted_schemes"])
    for dates, words in (({"valid_until": "2028-06-30"}, "expires 2028-06-30, before delivery ends 2028-12-31"),
                         ({"valid_from": "2028-03-01"}, "valid only from 2028-03-01; delivery starts 2028-01-01"),
                         ({"valid_from": None, "valid_until": None}, "states no validity dates")):
        a = cx.assess(req, _with(certificates=[{**iscc, **dates}]))
        o = cx.outcome_of(a, "accepted_schemes")
        assert (o["outcome"], a["status"]) == ("needs_evidence", "needs_evidence") and words in o["reason"], o
    assert _outcome(cx.assess(req, LISTING), "accepted_schemes") == "compatible"
    short = _with(certificates=[{**iscc, "valid_until": "2028-06-30"}])
    assert _outcome(cx.assess(_rfq(regimes=["ISCC EU"]), short), "regimes") == "needs_evidence"
