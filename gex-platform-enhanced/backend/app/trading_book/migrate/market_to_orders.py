"""
M3 — the market's own tables (offers, rfqs, matches) to the order model (spec §8 M3; Phase 3).

Phase 0 Q8, decided by JML 2026-11-06:

  offers   DRAFT -> draft   OPEN -> open   MATCHED -> filled   SETTLED -> filled
           WITHDRAWN -> cancelled   (EXPIRED -> expired: the market's own expiry)
  rfqs     draft -> draft   open -> published   matched -> closed
           withdrawn -> withdrawn   expired -> expired   cancelled -> withdrawn
  matches  pending -> an open invited proposal   declined / superseded / cancelled
           -> a cancelled one (its reason kept)   accepted -> STOP: its contract is in
           `contracts` (063) and must be carried by hand

Any other value, a listing whose token or seller cannot be resolved, or a match
whose proposer cannot be named: the run stops and reports — nothing is guessed,
and with --execute nothing is written until every row converts. Idempotent: a
row already converted (its id kept as the new row's id) is skipped. On
2026-11-10 there is nothing to convert (0 rows in all three tables).

Alembic 091 (M6) drops the three tables and refuses to while any row has no
converted counterpart — so on a database that still holds market rows (another
deployment, an older dump) run this with --execute at 090, before 091. Once 091
has run there is nothing left for it to read. Its test went with the tables
(the dead-table precedent); the mapping it applied is Q8, above.

    python -m app.trading_book.migrate.market_to_orders --dry-run
    python -m app.trading_book.migrate.market_to_orders --execute
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from app.trading_book import record

OFFER_STATE = {"DRAFT": "draft", "OPEN": "open", "MATCHED": "filled", "SETTLED": "filled",
               "WITHDRAWN": "cancelled", "EXPIRED": "expired"}
RFQ_STATE = {"draft": "draft", "open": "published", "matched": "closed", "withdrawn": "withdrawn",
             "expired": "expired", "cancelled": "withdrawn"}
MATCH_STATE = {"pending": "open", "declined": "cancelled", "superseded": "cancelled", "cancelled": "cancelled"}
ACTOR = "MIGRATION_M3_MARKET_TO_ORDERS"


def _uuid(v) -> str:
    """Keep a legacy id when it is a uuid; otherwise derive a stable one from it."""
    try:
        return str(uuid.UUID(str(v)))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"gex-market:{v}"))


def _exists(conn, table: str, row_id: str) -> bool:
    return bool(record._row(conn, f"SELECT 1 AS x FROM {table} WHERE id = ?", (row_id,)))


def run(conn, execute: bool) -> dict:
    from app.core.market_engine import market_terms

    report = {"offers": [], "rfqs": [], "matches": [], "skipped": [], "stopped": {}}

    def stop(kind, rid, why):
        report["stopped"][f"{kind}:{rid}"] = why

    for o in record._rows(conn, "SELECT o.*, t.capacity_id, t.certification_pathway, t.carbon_intensity_gco2e_mj, "
                                "c.project_id AS project, p.owner_tenant_id FROM offers o LEFT JOIN tokens t "
                                "ON t.id = o.token_id LEFT JOIN capacities c ON c.id = t.capacity_id "
                                "LEFT JOIN projects p ON p.project_id = c.project_id ORDER BY o.id"):
        new_id, state = _uuid(o["id"]), (o.get("listing_state") or "DRAFT")
        if _exists(conn, "tb_order", new_id):
            report["skipped"].append(f"offer:{o['id']}")
            continue
        if state not in OFFER_STATE:
            stop("offer", o["id"], f"listing state {state!r} has no mapping")
            continue
        if not o["owner_tenant_id"]:
            stop("offer", o["id"], "its token's project, and so its seller, cannot be resolved")
            continue
        if execute:
            terms = market_terms(conn, molecule=o["molecule"], volume_mtpd=o["volume_mtpd"],
                                 price_eur_kg=o["price_eur_kg"], delivery_start=o["delivery_start"],
                                 delivery_end=o["delivery_end"])
            w = record.write_terms(conn, terms, o["owner_tenant_id"], freeze=OFFER_STATE[state] != "draft")
            conn.execute("INSERT INTO tb_order (id, owner_id, side, terms_id, order_type, valid_until, status, "
                         "visibility, token_id, correlation_id, location, created_by_user) VALUES "
                         "(?, ?, 'sell', ?, 'firm', ?, ?, 'platform', ?, ?, ?, ?)",
                         (new_id, record.counterparty_for(conn, o["owner_tenant_id"]), w["terms_id"],
                          str(o["delivery_end"])[:10] + "T23:59:59+00:00", OFFER_STATE[state], o["token_id"],
                          o["correlation_id"], o["location"], ACTOR))
            conn.execute("INSERT INTO tb_order_event (order_id, to_status, actor_id, reason) VALUES (?, ?, ?, ?)",
                         (new_id, OFFER_STATE[state], ACTOR, f"converted from offer {o['id']} ({state})"))
        report["offers"].append(o["id"])

    for r in record._rows(conn, "SELECT * FROM rfqs ORDER BY id"):
        new_id = _uuid(r["id"])
        if _exists(conn, "tb_rfq", new_id):
            report["skipped"].append(f"rfq:{r['id']}")
            continue
        if r["status"] not in RFQ_STATE:
            stop("rfq", r["id"], f"status {r['status']!r} has no mapping")
            continue
        if execute:
            terms = market_terms(conn, molecule=r["molecule"], volume_mtpd=r["volume_mtpd"],
                                 price_eur_kg=r["max_price_eur_kg"], delivery_start=r["delivery_start"],
                                 delivery_end=r["delivery_end"])
            w = record.write_terms(conn, terms, r["buyer_company_id"], freeze=RFQ_STATE[r["status"]] != "draft")
            conn.execute("INSERT INTO tb_rfq (id, requester_id, side, terms_id, valid_until, status, buyer_name, "
                         "buyer_contact, location, compliance_requirements, correlation_id, created_by_user) "
                         "VALUES (?, ?, 'buy', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (new_id, record.counterparty_for(conn, r["buyer_company_id"]), w["terms_id"],
                          str(r["delivery_end"])[:10] + "T23:59:59+00:00", RFQ_STATE[r["status"]], r["buyer_name"],
                          r["buyer_contact"], r["location"],
                          r["compliance_requirements"] if isinstance(r["compliance_requirements"], str)
                          else json.dumps(r["compliance_requirements"] or []), r["correlation_id"], r["created_by"]))
        report["rfqs"].append(r["id"])

    for m in record._rows(conn, "SELECT m.*, u.company_id AS proposer FROM matches m LEFT JOIN auth_users u "
                                "ON u.user_id = m.created_by ORDER BY m.id"):
        new_id = _uuid(m["id"])
        if _exists(conn, "tb_order", new_id):
            report["skipped"].append(f"match:{m['id']}")
            continue
        if m["status"] == "accepted":
            stop("match", m["id"], "an accepted match's contract is in `contracts` (063): carry it by hand")
            continue
        if m["status"] not in MATCH_STATE:
            stop("match", m["id"], f"status {m['status']!r} has no mapping")
            continue
        if m["proposer"] not in (m["seller_company_id"], m["buyer_company_id"]):
            stop("match", m["id"], "its proposer (created_by) is neither the seller nor the buyer")
            continue
        if execute:
            other = m["buyer_company_id"] if m["proposer"] == m["seller_company_id"] else m["seller_company_id"]
            terms = market_terms(conn, molecule=m["molecule"], volume_mtpd=m["volume_mtpd"],
                                 price_eur_kg=m["price_eur_kg"], delivery_start=m["delivery_start"],
                                 delivery_end=m["delivery_end"])
            w = record.write_terms(conn, terms, m["proposer"])
            conn.execute("INSERT INTO tb_order (id, owner_id, side, terms_id, order_type, all_or_nothing, valid_until, "
                         "status, rfq_id, visibility, token_id, correlation_id, listing_order_id, match_score, "
                         "created_by_user) VALUES (?, ?, ?, ?, 'firm', true, ?, ?, ?, 'invited', ?, ?, ?, ?, ?)",
                         (new_id, record.counterparty_for(conn, m["proposer"]),
                          "sell" if m["proposer"] == m["seller_company_id"] else "buy", w["terms_id"],
                          str(m["delivery_end"])[:10] + "T23:59:59+00:00", MATCH_STATE[m["status"]],
                          _uuid(m["rfq_id"]), m["token_id"], m["correlation_id"], _uuid(m["offer_id"]),
                          m["match_score"], m["created_by"]))
            conn.execute("INSERT INTO tb_order_invitee (order_id, counterparty_id) VALUES (?, ?)",
                         (new_id, record.counterparty_for(conn, other)))
            conn.execute("INSERT INTO tb_order_event (order_id, to_status, actor_id, reason) VALUES (?, ?, ?, ?)",
                         (new_id, "open", m["created_by"], "proposal: the proposer's acceptance (converted)"))
            if MATCH_STATE[m["status"]] == "cancelled":
                conn.execute("INSERT INTO tb_order_event (order_id, from_status, to_status, actor_id, reason) "
                             "VALUES (?, 'open', 'cancelled', ?, ?)", (new_id, ACTOR, f"{m['status']} (converted)"))
        report["matches"].append(m["id"])
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = ap.parse_args(argv)
    from app.core import market_engine as me

    conn = me._conn()
    try:
        report = run(conn, execute=False)                 # always check every row first
        if args.execute and not report["stopped"]:
            report = run(conn, execute=True)
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    print(f"offers {len(report['offers'])}, rfqs {len(report['rfqs'])}, matches {len(report['matches'])}, "
          f"already converted {len(report['skipped'])}, stopped {len(report['stopped'])}"
          + (" (dry run: nothing written)" if args.dry_run else ""))
    for key, why in report["stopped"].items():
        print(f"  STOPPED {key}: {why}")
    return 1 if report["stopped"] else 0


if __name__ == "__main__":
    sys.exit(main())
