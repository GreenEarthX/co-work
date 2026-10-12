#!/usr/bin/env python3
"""Attack A — "Advance a project despite missing land control or safety approvals"
(GEX Persona-Based Adversarial Testing Prompt Library, §2 Producer).

Runs the REAL platform app in-process (routing, ABAC middleware, evidence write
validation, evidence store, audit events) against a THROWAWAY SQLite store, and
evaluates through the LIVE gate engine on :8001 (a stateless computation).

Isolation, by construction:
  * SQLITE_DB_PATH -> a temp file; every *_DB_BACKEND switch pinned to sqlite
    (same method as tests/conftest.py::isolated_store);
  * DATABASE_URL / ALEMBIC_DATABASE_URL -> an address that cannot connect, so an
    accidental PostgreSQL path fails loudly instead of writing the dev database.
Stubbed (the canonical projects table is PostgreSQL-only): the project's owner
profile and its physical/financing context. Everything else is the real code.
All records are synthetic and labelled TEST / ADVERSARIAL.
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import types

BACKEND = '/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend'
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

TMP = os.path.realpath(tempfile.mkdtemp(prefix='gex_attackA_TEST_'))  # system temp, never the repo
DB = os.path.join(TMP, 'attackA_TEST.db')
SWITCHES = sorted(set(re.findall(r'^\s+([A-Z_]+_DB_BACKEND)\s*:', open('app/core/config.py').read(), re.M)))
os.environ['SQLITE_DB_PATH'] = DB
for s in SWITCHES + ['ECOSYSTEM_DB_BACKEND']:
    os.environ[s] = 'sqlite'
DEAD = 'postgresql://attack_harness_no_pg@127.0.0.1:9/no_such_database'
os.environ['DATABASE_URL'] = DEAD
os.environ['ALEMBIC_DATABASE_URL'] = DEAD
os.environ.pop('CANONICAL_DATABASE_URL', None)

from app.core.config import settings  # noqa: E402

assert os.path.realpath(settings.SQLITE_DB_PATH) == DB, settings.SQLITE_DB_PATH
assert SWITCHES and all(getattr(settings, s) == 'sqlite' for s in SWITCHES), SWITCHES
assert getattr(settings, 'DATABASE_URL', DEAD) == DEAD

from app.core import auth  # noqa: E402

_c = sqlite3.connect(DB)
_c.row_factory = sqlite3.Row
auth._ensure_tables(_c)
_c.close()

from app.api.v1 import routes_bankability_proxy as proxy  # noqa: E402

_c = proxy._get_db()
proxy._ensure_tables(_c)
_c.close()

from app.core import project_registry as reg  # noqa: E402
import app.core.abac_middleware as mw  # noqa: E402

PID = 'proj_TEST_attack_a'
OWNER = 'TEST Adversarial Dev'
OUTSIDER = 'TEST Unrelated Co'
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name='TEST Attack A e-Methanol',
                                   owner_company_name=OWNER, associated_company_names=(),
                                   jurisdiction='DE')
CTX = types.SimpleNamespace(power_model='GRID_CONNECTED', phase='FEED', financing_model='PROJECT_FINANCE')


def _profile(pid):
    return PROFILE if reg.normalize_project_id(pid) == PID else None


def _context(pid):
    return CTX if reg.normalize_project_id(pid) == PID else None


mw.get_project_profile = _profile
reg.get_project_profile = _profile
reg.get_effective_context = _context

from app.core.auth import create_access_token  # noqa: E402


def token(user_id, company, actor, business_function='EXECUTIVE', audits=()):
    subject = dict(user_id=user_id, email=f'{user_id}@test.invalid', company_id=reg.company_slug(company),
                   company_name=company, company_type='PRODUCER', service_type=None,
                   business_function=business_function, user_name=f'TEST {user_id}',
                   clearance_level='STANDARD', jurisdiction='DE', kyc_status='VERIFIED',
                   nda_signed_with=[], assigned_audits=list(audits),
                   actor_type_per_project={PID: [actor]})
    return create_access_token(subject)[0]


PRODUCER = token('u_TEST_producer', OWNER, 'PRODUCER')
OUTSIDER_PRODUCER = token('u_TEST_outsider', OUTSIDER, 'PRODUCER')

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)  # no lifespan: no demo seeding, no startup side effects
LOG = []


def call(label, method, path, tok, body=None, params=None):
    headers = {'Authorization': f'Bearer {tok}'}
    r = client.request(method, path, headers=headers, json=body, params=params)
    try:
        data = r.json()
    except ValueError:
        data = {'raw': r.text[:300]}
    return r.status_code, data


def evaluate():
    code, snap = call('evaluate', 'GET', '/api/v1/bankability/evaluate', PRODUCER, params={'project_id': PID})
    if code != 200:
        return {'http': code, 'detail': snap}
    gates = snap.get('gate_evaluations') or []
    gates = list(gates.values()) if isinstance(gates, dict) else gates
    return {
        'http': code,
        'state': snap.get('current_state'),
        'state_label': snap.get('state_label'),
        'complete_gates': [g.get('gate_id', '')[:3].rstrip('_') for g in gates if g.get('is_complete')],
        'eligible_capital': [c.get('label') or c.get('capital_type') for c in snap.get('capital_unlocks', [])
                             if c.get('decision_eligible') or c.get('is_unlocked')],
        'offtake': (snap.get('offtake') or {}).get('level'),
        'epc': (snap.get('epc') or {}).get('level'),
    }


def write(label, key, status, maturity=None, submitted_by='TEST producer', notes=None, tok=None):
    body = {'project_id': PID, 'evidence_key': key, 'new_status': status,
            'submitted_by': submitted_by, 'notes': notes or 'TEST/ADVERSARIAL', 'maturity': maturity}
    code, data = call(label, 'POST', '/api/v1/bankability/evidence', tok or PRODUCER, body=body)
    detail = data.get('detail') if isinstance(data, dict) else data
    return code, (detail if code != 200 else 'accepted')


def record(step, attempt, expected, code, detail, state=None):
    row = {'step': step, 'attempt': attempt, 'expected_control': expected, 'http': code,
           'response': detail, 'engine_after': state}
    LOG.append(row)
    print(json.dumps(row, default=str)[:900])


# ── Baseline ────────────────────────────────────────────────────────────────
record('A0', 'Baseline: fresh TEST project, no evidence', 'State SPECULATIVE', 200, '-', evaluate())

# ── A1: land OPTION described as an executed lease (submission) ─────────────
code, d = write('A1', 'land_option_or_lease_executed', 'SUBMITTED', 'EXECUTED',
                notes='TEST/ADVERSARIAL: the document is a land OPTION, declared as an executed lease')
record('A1', 'Submit a land option declared EXECUTED (lease)', 'Accept as a claim; must not count until '
       'independently verified', code, d, evaluate())

# ── A2: the same producer verifies its own claim, under a spoofed reviewer name ─
code, d = write('A2', 'land_option_or_lease_executed', 'VERIFIED', 'EXECUTED',
                submitted_by='TEST Independent Certifier (spoofed name)')
record('A2', 'Producer marks its own land claim VERIFIED, naming a certifier as actor',
       'DENY: the party asserting must not verify (separation of duties)', code, d, evaluate())

# ── A2b: control that should hold — verification cannot raise maturity ─────
write('A2b-setup', 'zoning_compatibility_memo', 'SUBMITTED', 'INDICATIVE')
code, d = write('A2b', 'zoning_compatibility_memo', 'VERIFIED', 'EXECUTED')
record('A2b', 'Verify a memo while raising its declared maturity INDICATIVE -> EXECUTED',
       'DENY 422 VERIFICATION_CANNOT_RAISE_MATURITY', code, d)

# ── A3: complete G0 and G1 by self-verification ─────────────────────────────
G0 = ['zoning_compatibility_memo', 'stakeholder_map_v1', 'site_technical_suitability']
MAT = {'ppa_signed_or_term_sheet_evidence': 'INDICATIVE', 'technology_licensor_term_sheet': 'INDICATIVE'}
from app.core.bankability_engine import GATE_REGISTRY  # noqa: E402

G1 = next(g for g in GATE_REGISTRY if g.id.startswith('G1')).required_evidence
results = []
for key in G0 + list(G1):
    m = MAT.get(key) if key in MAT else ('EXECUTED' if key == 'land_option_or_lease_executed' else None)
    c1, _ = write('A3', key, 'SUBMITTED', m)
    c2, d2 = write('A3', key, 'VERIFIED', m)
    results.append((key, c1, c2, d2 if c2 != 200 else ''))
refused = [(k, c2, d) for k, c1, c2, d in results if c2 != 200]
record('A3', f'Self-verify every G0 and G1 item ({len(results)} writes, no document reviewed)',
       'DENY each VERIFIED write from the producer; state stays SPECULATIVE', 200 if not refused else 'mixed',
       {'refused': refused[:6], 'refused_count': len(refused)}, evaluate())

# ── A4: an application described as an approval; a sponsor letter as a permit ─
code, d = write('A4', 'eia_permit_granted', 'SUBMITTED', 'EXECUTED',
                notes='TEST/ADVERSARIAL: only the APPLICATION was filed; declared as granted')
code2, d2 = write('A4', 'eia_permit_granted', 'VERIFIED', 'EXECUTED')
code3, d3 = write('A4', 'construction_permit_granted', 'SUBMITTED', 'EXECUTED',
                  notes='TEST/ADVERSARIAL: sponsor representation letter offered as the permit')
code4, d4 = write('A4', 'construction_permit_granted', 'VERIFIED', 'EXECUTED')
record('A4', 'Permit application and a sponsor letter recorded as granted permits, then self-verified (G9)',
       'Distinguish application from approval; DENY self-verification', f'{code},{code2},{code3},{code4}',
       [d, d2, d3, d4], evaluate())

# ── A5: EPC engagement presented as an agreed-form contract ─────────────────
epc_items = [('epc_contract_fixed_price_or_capped_gmp', 'AGREED'), ('feed_complete_class3', None),
             ('technology_licence_process_guarantee', 'AGREED'), ('epc_security_package', 'AGREED'),
             ('liquidated_damages_schedule', None)]
epc_codes = []
for key, m in epc_items:
    c1, _ = write('A5', key, 'SUBMITTED', m, notes='TEST/ADVERSARIAL: EPC engagement letter only')
    c2, d2 = write('A5', key, 'VERIFIED', m)
    epc_codes.append((key, c1, c2))
code, d = call('A5', 'PUT', '/api/v1/bankability/terms', PRODUCER,
               body={'project_id': PID, 'card_type': 'epc', 'terms': {'contracting_model': 'LSTK'}})
record('A5', 'EPC engagement letter recorded as agreed-form EPC, FEED, licence and security; self-verified; '
       'EPC card set to LSTK', 'EPC must not reach E4 without independently verified documents',
       [c for _, _, c in epc_codes] + [code], d if code != 200 else 'card accepted', evaluate())

# ── A6: controls that should hold ───────────────────────────────────────────
code, d = write('A6a', 'land_option_or_lease_executed', 'VERIFIED', 'EXECUTED', tok=OUTSIDER_PRODUCER)
record('A6a', 'A producer from an unrelated company writes this project\'s evidence', 'DENY (not a stakeholder)',
       code, d)
code, d = write('A6b', 'cp_checklist_completed', 'VERIFIED', 'EFFECTIVE')
record('A6b', 'The producer writes a lender item (G10 conditions precedent)', 'DENY (not the gate owner)',
       code, d)
code, d = write('A6c', 'binding_offtake_contract_executed', 'VERIFIED', 'EXECUTED')
record('A6c', 'The producer writes the buyer-side offtake item (G4)', 'DENY (offtaker-owned gate)', code, d)

# ── A7: redeclare the financing model (owner-executive declaration, audited) ─
CTX.financing_model = 'BALANCE_SHEET'
record('A7', 'Simulated: owner executive redeclares PROJECT_FINANCE -> BALANCE_SHEET (PATCH /projects/{id}/context, '
       'allowed and audited; not executed here: PostgreSQL-only store)',
       'Allowed for the owner executive, audited; lender-only gates waived', 'simulated', '-', evaluate())
CTX.financing_model = 'PROJECT_FINANCE'

# ── Audit trail ─────────────────────────────────────────────────────────────
conn = proxy._get_db()
rows = [dict(r) for r in conn.execute("SELECT * FROM evidence_events WHERE project_id = ? ORDER BY id",
                                      (PID,)).fetchall()]
conn.close()
land = [r for r in rows if r.get('evidence_key') == 'land_option_or_lease_executed']
record('A8', 'Audit trail for the land item', 'Before/after, authenticated user, reason',
       200, {'events': land, 'total_events': len(rows)})

out = os.path.join(TMP, 'attackA_results.json')
json.dump({'db': DB, 'switches': SWITCHES, 'log': LOG}, open(out, 'w'), indent=2, default=str)
print('\nresults ->', out)
