"""
The lender evidence pack for one contract (GreenMesh Phase 1, Step 5).
=====================================================================
One JSON document per contract, assembled from the records — never typed — with a SHA-256
manifest. Every item carries a LABEL saying where its claim comes from:

  VERIFIED   computed from recorded data by GEX (a recomputed hash chain, a closed and
             verified period statement, a meter reconciliation, a computed correlation)
  DECLARED   stated by a party and recorded as stated (characteristics, settlements, an
             open period's provisional figures, an anchor receipt not re-checked here)
  MISSING    the record that would support it does not exist

and, where it is a check, a RESULT (PASS | FAIL). A VERIFIED item can FAIL: the label is
provenance, the result is the outcome. A declared value is never shown as verified.

COMPLIANCE is the section a lender relies on: per period behind the contract's tokens —
the closed custody period, inputs x conversion, metered production and electricity, and
the three RFNBO correlation checks. The lot's characteristics (GHG intensity, certificate,
RFNBO flag) stay DECLARED and sit OUTSIDE it: Phase 1 does not verify an LCA or a scheme
certificate, and the pack says so rather than counting them.

DELIVERIES (Phase 2 Step 5; pack version 2): one section item group per delivery on the
contract —
  quality         VERIFIED when the agreed inspector's certificate is on file and the computed
                  check passes (PASS) or fails (FAIL); DECLARED, FAIL under a waiver or a
                  resolution accepted on a failed certificate (D3); MISSING with no certificate
  title_transfer  VERIFIED from the recomputed contract event chain (PASS when it holds), or
                  MISSING while title has not passed (saying what it waits for)
  route, incoterm DECLARED: the parties' statements (MISSING when the terms name no Incoterm)
The contract's tokens come from its settlements AND its deliveries' draws (a delivery contract
may have no settlement: R2). `compliance_complete` additionally requires every delivery's
quality to be VERIFIED and PASS. Settlements are not linked to deliveries (settlement on a
delivery comes after Step 3), and each settlement item says so.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

PACK_VERSION = "3"        # 2: the delivery section (Phase 2 Step 5); 3: token lineage through splits (114)


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _clean(row: dict) -> dict:
    return {k: _iso(v) for k, v in row.items()}


def item(name: str, label: str, result: Optional[str] = None, **detail) -> dict:
    assert label in ("VERIFIED", "DECLARED", "MISSING"), label
    return {"item": name, "label": label, "result": result, **detail}


def _rows(conn, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ── sections ────────────────────────────────────────────────────────────────

def _contract_section(conn, c: dict) -> dict:
    from app.trading_book import record

    evs = record.events(conn, c["id"])
    items = [item("contract_record", "VERIFIED", contract_ref=c["contract_ref"], kind=c["kind"],
                  project_id=c["project_id"], owner_company_id=c["owner_company_id"],
                  verification_state=c["verification_state"])]
    if not evs:
        items.append(item("event_chain", "MISSING", reason="the contract has no events"))
    else:
        ok = record.chain_intact_events(c["contract_ref"], evs)
        items.append(item("event_chain", "VERIFIED", "PASS" if ok else "FAIL", events=len(evs),
                          head_hash=evs[-1]["event_hash"],
                          event_hashes=[e["event_hash"] for e in evs]))
    outbox = _rows(conn, "SELECT event_hash, status, ledger_network, ledger_topic_id, ledger_sequence_number, "
                         "anchored_at FROM ledger_anchor_outbox WHERE contract_id = ? ORDER BY created_at", (c["id"],))
    anchored = [o for o in outbox if o["status"] == "ANCHORED"]
    if anchored and len(anchored) == len(outbox):
        items.append(item("ledger_anchor", "DECLARED", receipts=[_clean(o) for o in anchored],
                          reason="anchor receipts are recorded; re-check them on the ledger with "
                                 "scripts/verify_anchor.py"))
    else:
        items.append(item("ledger_anchor", "MISSING", outbox=len(outbox), anchored=len(anchored),
                          reason="not every contract event is anchored (LEDGER_ANCHOR_BACKEND may be none)"))
    return {"items": items}


def _allocation_chain_ok(allocs: list[dict]) -> bool:
    prev = None
    for a in allocs:
        if a["prev_hash"] != prev:
            return False
        if _h({"allocation_id": a["allocation_id"], "lot_id": a["lot_id"], "token_id": a["token_id"],
               "volume_kg": a["volume_kg"], "prev_hash": prev, "timestamp": a["created_at"]}) != a["allocation_hash"]:
            return False
        prev = a["allocation_hash"]
    return True


def _compliance_items(conn, p: dict) -> list[dict]:
    from app.core import custody_ledger as cl

    pid = p["period_id"]
    if p["status"] != "CLOSED":
        return [item(n, "DECLARED", period_id=pid, reason="the accounting period is still open: its figures "
                                                          "are provisional")
                for n in ("custody_period", "conversion", "metered_production", "metered_electricity",
                          "temporal_correlation", "geographic_correlation", "additionality")]
    st = p["statement"]
    v = cl.verify_period(conn, pid)
    out = [item("custody_period", "VERIFIED", "PASS" if v["valid"] else "FAIL", period_id=pid,
                statement_hash=p["statement_hash"], closing_balance_kg=st["closing_balance_kg"],
                identity=st["identity"], checks=v["checks"])]
    conv = st["conversion"]
    if conv["check"] == "NO_FACTOR":
        out.append(item("conversion", "MISSING", period_id=pid, reason="no conversion factor in force"))
    else:
        out.append(item("conversion", "VERIFIED", "PASS" if conv["check"] == "WITHIN_INPUTS" else "FAIL",
                        period_id=pid, **conv))
    for name, key in (("metered_production", "production"), ("metered_electricity", "electricity")):
        m = (st.get("meter_reconciliation") or {}).get(key)
        if not m or m["status"] == "UNVERIFIED":
            out.append(item(name, "MISSING", period_id=pid, reason=(m or {}).get("reason", "not reconciled")))
        else:
            out.append(item(name, "VERIFIED", "PASS" if m["status"] == "RECONCILED" else "FAIL", period_id=pid,
                            declared=m["declared"], metered=m["metered"], unit=m["unit"],
                            tolerance_fraction=m["tolerance_fraction"], tolerance_source=m["tolerance_source"]))
    corr = st.get("rfnbo_correlation") or {}
    emitted = 0
    for name, key in (("temporal_correlation", "temporal"), ("geographic_correlation", "geographic"),
                      ("additionality", "additionality"), ("upstream_hydrogen", "upstream_hydrogen")):
        r = corr.get(key)
        if key == "upstream_hydrogen" and not r:
            continue                                  # a statement closed before 101
        if r and r["status"] == "NOT_APPLICABLE":     # counts for nothing; not an item
            continue
        emitted += 1
        if not r or r["status"] == "UNVERIFIED":
            out.append(item(name, "MISSING", period_id=pid, reason=(r or {}).get("reason", "not computed"),
                            **({"inputs": r["inputs"]} if r and "inputs" in r else {})))
        else:
            out.append(item(name, "VERIFIED", r["status"], period_id=pid, reason=r["reason"],
                            rules_used=corr.get("rules_used"),
                            **({"inputs": r["inputs"]} if "inputs" in r else {})))
    if not emitted:
        out.append(item("rfnbo_correlation", "MISSING", period_id=pid,
                        reason="no correlation check applies: no hydrogen output, no certified electricity "
                               "or hydrogen input"))
    return out


def build(conn, contract_id: str) -> Optional[dict]:
    """The pack, or None if the caller may not read the contract (RLS decides)."""
    c = conn.execute("SELECT * FROM tb_contract WHERE id = ?", (contract_id,)).fetchone()
    if not c:
        return None
    c = dict(c)
    settlements = _rows(conn, "SELECT * FROM settlement_events WHERE contract_id = ? ORDER BY created_at",
                        (contract_id,))
    deliveries = _rows(conn, "SELECT * FROM deliveries WHERE contract_id = ? ORDER BY window_start, id", (contract_id,))
    drawn = _rows(conn, "SELECT DISTINCT x.token_id FROM delivery_draw x JOIN deliveries d ON d.id = x.delivery_id "
                        "WHERE d.contract_id = ?", (contract_id,)) if deliveries else []
    token_ids = sorted({s["token_id"] for s in settlements if s.get("token_id")} | {r["token_id"] for r in drawn})

    tokens, custody, compliance, declared = [], [], [], []
    periods: dict[str, dict] = {}
    for tid in token_ids:
        t = conn.execute("SELECT id, lifecycle_state, mass_balance_lot_id, holder_company_id, parent_token_id "
                         "FROM tokens WHERE id = ?", (tid,)).fetchone()
        if not t:
            tokens.append(item("token", "MISSING", token_id=tid, reason="token not readable"))
            continue
        t = dict(t)
        lot = conn.execute("SELECT * FROM mass_balance_lots WHERE lot_id = ?",
                           (t["mass_balance_lot_id"],)).fetchone() if t["mass_balance_lot_id"] else None
        if not lot:
            tokens.append(item("token_lineage", "MISSING", token_id=tid, lifecycle_state=t["lifecycle_state"],
                               reason="the token is backed by no custody lot"))
            continue
        lot = dict(lot)
        allocs = _rows(conn, "SELECT * FROM mass_balance_allocations WHERE lot_id = ? ORDER BY created_at",
                       (lot["lot_id"],))
        # A carved token (market split, alembic 114; delivery title, 109) holds part of an ancestor's
        # allocation: walk the recorded splits up to the token the lot was allocated to. Every step
        # must be a recorded split, or the lineage is MISSING.
        holder_id, via, node = tid, [], t
        mine = [a for a in allocs if a["token_id"] == holder_id]
        while not mine and node.get("parent_token_id"):
            step = conn.execute("SELECT reason, event_hash, kg FROM token_split WHERE child_token_id = ?",
                                (holder_id,)).fetchone()
            if not step:
                break
            via.append({"child": holder_id, "reason": dict(step).get("reason", "delivery_title"),
                        "event_hash": step["event_hash"]})
            holder_id = node["parent_token_id"]
            node = dict(conn.execute("SELECT id, parent_token_id FROM tokens WHERE id = ?", (holder_id,)).fetchone() or {})
            mine = [a for a in allocs if a["token_id"] == holder_id]
        chain_ok = _allocation_chain_ok(allocs)
        kg = (sum(float(a["volume_kg"]) for a in mine) if not via
              else float(conn.execute("SELECT app_token_kg(?) AS kg", (tid,)).fetchone()["kg"] or 0))
        tokens.append(item("token_lineage", "VERIFIED" if mine else "MISSING",
                           ("PASS" if chain_ok else "FAIL") if mine else None, token_id=tid,
                           lifecycle_state=t["lifecycle_state"], lot_id=lot["lot_id"],
                           allocated_kg=kg, allocated_to=holder_id, via_splits=via,
                           allocation_hashes=[a["allocation_hash"] for a in mine]))
        custody.append(item("lot", "DECLARED", lot_id=lot["lot_id"], period_id=lot["period_id"],
                            molecule=lot["molecule"], total_volume_kg=lot["total_volume_kg"],
                            production_date=lot["production_date"], conversion_check=lot["conversion_check"],
                            meter_check_at_creation=lot["meter_check"],
                            reason="the lot's volume is the producer's declaration; compliance checks it"))
        declared.append(item("lot_characteristics", "DECLARED", lot_id=lot["lot_id"],
                             characteristics=lot["characteristics"],
                             carbon_intensity_gco2e_mj=lot["carbon_intensity_gco2e_mj"],
                             reason="stated by the producer; Phase 1 verifies no LCA and no scheme certificate"))
        if lot["period_id"] and lot["period_id"] not in periods:
            periods[lot["period_id"]] = dict(conn.execute("SELECT * FROM coc_period WHERE period_id = ?",
                                                          (lot["period_id"],)).fetchone())
        if not lot["period_id"]:
            compliance.append(item("custody_period", "MISSING", lot_id=lot["lot_id"],
                                   reason="the lot belongs to no accounting period"))
    for p in periods.values():
        compliance.extend(_compliance_items(conn, p))
    if not token_ids:
        compliance.append(item("custody_period", "MISSING", reason="no settled or delivered token names this contract"))

    settlement_items = [item("settlement", "DECLARED", settlement_id=s["settlement_id"], token_id=s["token_id"],
                             status=s["settlement_status"], volume_kg=s["volume_kg"],
                             total_amount=s["total_amount"], currency=s["currency"], audit_hash=s["audit_hash"],
                             delivery_id=None,
                             **({"delivery_link": "settlements are not linked to deliveries yet (settlement on a "
                                                  "delivery comes after Phase 2 Step 3)"} if deliveries else {}))
                        for s in settlements] or [item("settlement", "MISSING", reason="no settlement recorded")]
    delivery_items = _delivery_items(conn, c, deliveries)
    evidence = [item("evidence", "VERIFIED" if e["verification_state"] == "VERIFIED" else "DECLARED",
                     evidence_id=e["evidence_id"], category=e["category"], verification_state=e["verification_state"],
                     hash=e["hash"])
                for e in _rows(conn, "SELECT * FROM evidence_ledger WHERE project_id = ? ORDER BY timestamp",
                               (c["project_id"],))] if c.get("project_id") else []

    sections = {"contract": _contract_section(conn, c), "tokens": {"items": tokens},
                "custody": {"items": custody}, "compliance": {"items": compliance},
                "declared_characteristics": {"items": declared}, "settlement": {"items": settlement_items},
                "deliveries": {"items": delivery_items},
                "evidence_ledger": {"items": evidence}}
    sections = json.loads(json.dumps(sections, default=str))     # one canonical form, hashed as sent

    def tally(items: list[dict]) -> dict:
        return {k: sum(1 for i in items if i["label"] == k) for k in ("VERIFIED", "DECLARED", "MISSING")} | {
            "FAIL": sum(1 for i in items if i.get("result") == "FAIL")}

    manifest = {"sections": {k: _h(v) for k, v in sections.items()}}
    manifest["pack_sha256"] = _h({"contract_id": contract_id, "pack_version": PACK_VERSION,
                                  "sections": manifest["sections"]})
    compliance_tally = tally(compliance)
    quality = [i for i in delivery_items if i["item"] == "quality"]
    deliveries_ok = all(i["label"] == "VERIFIED" and i.get("result") == "PASS" for i in quality)
    return {"pack_version": PACK_VERSION, "contract_id": contract_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {"compliance": compliance_tally,
                        "compliance_complete": bool(compliance) and compliance_tally["DECLARED"] == 0
                        and compliance_tally["MISSING"] == 0 and compliance_tally["FAIL"] == 0 and deliveries_ok,
                        "deliveries_quality_verified": deliveries_ok if quality else None,
                        "all_sections": {k: tally(v["items"]) for k, v in sections.items()}},
            "sections": sections, "manifest": manifest}


def _delivery_items(conn, c: dict, deliveries: list[dict]) -> list[dict]:
    """Per delivery: quality, title_transfer, route, incoterm (Phase 2 Step 5)."""
    from app.trading_book import record

    if not deliveries:
        return []
    evs = record.events(conn, str(c["id"]))
    chain_ok = record.chain_intact_events(c["contract_ref"], evs) if evs else False
    out = []
    for d in deliveries:
        mine = [e for e in evs if e.get("delivery_id") == d["id"]]
        notes = {e["event_type"]: json.loads(e["note"] or "{}") for e in mine}   # the latest of each type
        cert = notes.get("DELIVERY_FACT_CERTIFIED")
        accepted = notes.get("DELIVERY_ACCEPTED")
        base = {"delivery_id": d["id"], "status": d["status"]}
        if cert is None:
            out.append(item("quality", "MISSING", **base, reason="no certificate from an agreed inspector"))
        else:
            on_file = conn.execute("SELECT 1 AS x FROM delivery_document WHERE delivery_id = ? AND kind = "
                                   "'INSPECTION_CERTIFICATE' AND sha256 = ?", (d["id"], cert["document_sha256"])).fetchone()
            if not on_file:
                out.append(item("quality", "MISSING", **base, reason="the certificate named is not on file"))
            elif accepted and accepted.get("label") == "DECLARED":
                out.append(item("quality", "DECLARED", "FAIL", **base, basis=accepted.get("basis"),
                                inspector_company_id=d.get("inspector_company_id"), certificate_result=cert["result"],
                                certificate_sha256=cert["document_sha256"],
                                reason="accepted on a failed certificate by both parties' waiver (D3)"))
            else:
                out.append(item("quality", "VERIFIED", cert["result"], **base,
                                inspector_company_id=d.get("inspector_company_id"),
                                certificate_sha256=cert["document_sha256"], parameters=cert.get("results")))
        title = [e for e in mine if e["event_type"] == "DELIVERY_TITLE_TRANSFERRED"]
        if title:
            t = json.loads(title[-1]["note"] or "{}")
            out.append(item("title_transfer", "VERIFIED", "PASS" if chain_ok else "FAIL", **base,
                            event_hash=title[-1]["event_hash"], title_passes=t.get("title_passes"),
                            labels=t.get("labels", []), transfers=t.get("transfers", [])))
        else:
            out.append(item("title_transfer", "MISSING", **base, title_passes=d.get("title_passes"),
                            reason="title has not passed"))
        out.append(item("route", "DECLARED", **base, transport_mode=d["transport_mode"],
                        origin=d["origin_locode"] or d["origin_facility_id"],
                        destination=d["destination_locode"] or d["destination_facility_id"]))
        if d["incoterm"]:
            out.append(item("incoterm", "DECLARED", **base, incoterm=d["incoterm"], named_place=d["named_place"],
                            shipment_point=d.get("shipment_point")))
        else:
            out.append(item("incoterm", "MISSING", **base, reason="the confirmed terms name no Incoterm"))
    return out
