"""
`gex_export_v1` — GEX's own export format (Phase 2 Step 6). NOT a registry's or a scheme's format:
no public field-level specification of CertifHy, ISCC, the UDB or the AIB hub was found
(docs/GREENMESH_CONNECTORS_RESEARCH.md, 13 Nov 2026), so no registry field name is invented here.

The payload carries ONLY VERIFIED items of the evidence pack (compliance, token lineage, delivery
quality and title), each with the hashes that let a certifier re-check it, plus the pack's
SHA-256. What is DECLARED (lot characteristics, route, Incoterm, settlements) is not carried as
a claim; the payload lists what it left out, so a reader cannot mistake absence for proof.
"""
from __future__ import annotations


class GexExportV1:
    name = "gex_export_v1"

    def build(self, pack: dict) -> dict:
        sections = pack["sections"]
        verified, omitted = {}, {}
        for section in ("compliance", "tokens", "deliveries", "contract"):
            items = sections.get(section, {}).get("items", [])
            verified[section] = [i for i in items if i["label"] == "VERIFIED"]
            omitted[section] = sum(1 for i in items if i["label"] != "VERIFIED")
        for section in ("custody", "declared_characteristics", "settlement", "evidence_ledger"):
            omitted[section] = len(sections.get(section, {}).get("items", []))
        return {"format": self.name, "format_note": "GEX's own export format, not a registry's",
                "contract_id": pack["contract_id"], "pack_version": pack["pack_version"],
                "pack_sha256": pack["manifest"]["pack_sha256"], "section_sha256": pack["manifest"]["sections"],
                "verified": verified,
                "not_carried": {k: v for k, v in omitted.items() if v},
                "not_carried_reason": "DECLARED or MISSING items are not claims; re-read them in the pack"}
