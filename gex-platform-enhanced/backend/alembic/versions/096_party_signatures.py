"""Party signatures on the contract record (Phase 5 of "One contract record").

Revision ID: 096
Revises: 095

WHY
---
A counterparty's confirmation rests today on a session token that GEX itself signs.
From here a CONFIRMED or DISPUTED event MAY carry the party's own signature over the
event hash, by a key the party registered, so the confirmation stands on the party's
key and not on GEX's word. Recorded and verified, not yet required
(REQUIRE_PARTY_SIGNATURE, default false). No wallet, no eIDAS seal validation yet; the
scheme column is ready for them.

WHAT
----
party_signing_key   A company's public keys (ed25519). Proposed by an EXECUTIVE,
                    activated by a SECOND executive of the same company (four eyes,
                    enforced here by trigger as well as in the application), revoked
                    by an executive; every step in the platform event ledger. The key
                    material and its reference never change; no row is deleted; the
                    states move PROPOSED -> ACTIVE | REJECTED, ACTIVE -> REVOKED only.
tb_contract_event   signature, signature_scheme (none | ed25519), signer_key_ref —
                    BESIDE the event hash, not inside it: the signature covers
                    event_hash, so existing hashes and anchors are unchanged. A signed
                    event must be CONFIRMED or DISPUTED and name an ACTIVE key of the
                    event's own company (trigger; the cryptographic check is the
                    application's, on write).

TENANCY
-------
A company reads and writes its own keys (FORCED RLS, WITH CHECK); GEX staff read
them (public keys, no secret). Verification reads any key through one SECURITY
DEFINER lookup with a pinned search_path. gex_app holds SELECT, INSERT and column
UPDATE on the lifecycle columns only. Asserted below.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "096"
down_revision: Union[str, None] = "095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
LIFECYCLE = ("status", "approved_by", "approved_at", "revoked_by", "revoked_at", "revoke_reason")


def _q(sql: str, params: dict | None = None):
    return op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    conn = op.get_bind()
    _q("""CREATE TABLE party_signing_key (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           company_id text NOT NULL REFERENCES tenants(company_id),
           key_ref text NOT NULL UNIQUE,
           scheme text NOT NULL CHECK (scheme IN ('ed25519')),
           public_key text NOT NULL UNIQUE,
           label text,
           status text NOT NULL DEFAULT 'PROPOSED' CHECK (status IN ('PROPOSED', 'ACTIVE', 'REJECTED', 'REVOKED')),
           proposed_by text NOT NULL,
           proposed_at timestamptz NOT NULL DEFAULT now(),
           approved_by text,
           approved_at timestamptz,
           revoked_by text,
           revoked_at timestamptz,
           revoke_reason text,
           CONSTRAINT ck_party_key_four_eyes CHECK (approved_by IS NULL OR approved_by <> proposed_by),
           CONSTRAINT ck_party_key_active CHECK (status NOT IN ('ACTIVE', 'REVOKED') OR approved_by IS NOT NULL),
           CONSTRAINT ck_party_key_revoked CHECK ((status = 'REVOKED') = (revoked_by IS NOT NULL)))""")
    _q("""CREATE FUNCTION party_signing_key_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'PARTY_KEY_KEPT: a signing key is revoked, never removed' USING ERRCODE = 'check_violation';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'PROPOSED' OR NEW.approved_by IS NOT NULL OR NEW.revoked_by IS NOT NULL THEN
              RAISE EXCEPTION 'PARTY_KEY_STARTS_PROPOSED: a key is proposed first, then activated by a second person'
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.company_id <> OLD.company_id OR NEW.key_ref <> OLD.key_ref OR NEW.scheme <> OLD.scheme
             OR NEW.public_key <> OLD.public_key OR NEW.proposed_by <> OLD.proposed_by
             OR NEW.proposed_at <> OLD.proposed_at OR NEW.label IS DISTINCT FROM OLD.label THEN
            RAISE EXCEPTION 'PARTY_KEY_FIXED: a registered key never changes' USING ERRCODE = 'check_violation';
          END IF;
          IF NOT ((OLD.status = NEW.status AND OLD.approved_by IS NOT DISTINCT FROM NEW.approved_by
                   AND OLD.revoked_by IS NOT DISTINCT FROM NEW.revoked_by)
                  OR (OLD.status = 'PROPOSED' AND NEW.status IN ('ACTIVE', 'REJECTED'))
                  OR (OLD.status = 'ACTIVE' AND NEW.status = 'REVOKED' AND NEW.approved_by = OLD.approved_by)) THEN
            RAISE EXCEPTION 'PARTY_KEY_TRANSITION: % -> % is not a key transition', OLD.status, NEW.status
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER party_signing_key_guard BEFORE INSERT OR UPDATE OR DELETE ON party_signing_key "
       "FOR EACH ROW EXECUTE FUNCTION party_signing_key_guard()")
    _q("ALTER TABLE party_signing_key ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE party_signing_key FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY party_signing_key_read ON party_signing_key FOR SELECT USING ({ADMIN} OR company_id = {ME})")
    _q(f"CREATE POLICY party_signing_key_insert ON party_signing_key FOR INSERT WITH CHECK (company_id = {ME})")
    _q(f"CREATE POLICY party_signing_key_update ON party_signing_key FOR UPDATE USING (company_id = {ME}) "
       f"WITH CHECK (company_id = {ME})")
    _q("REVOKE ALL ON party_signing_key FROM PUBLIC, gex_app")
    _q("GRANT SELECT, INSERT ON party_signing_key TO gex_app")
    _q(f"GRANT UPDATE ({', '.join(LIFECYCLE)}) ON party_signing_key TO gex_app")
    # Verification and the readouts may need ANY company's public key: one lookup, no more.
    _q("""CREATE FUNCTION app_party_signing_key(p_key_ref text)
          RETURNS TABLE (company_id text, scheme text, public_key text, status text)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
          SELECT k.company_id, k.scheme, k.public_key, k.status FROM party_signing_key k WHERE k.key_ref = p_key_ref
        $$""")

    # ── the signature beside the event hash ─────────────────────────────────
    _q("ALTER TABLE tb_contract_event ADD COLUMN signature text")
    _q("ALTER TABLE tb_contract_event ADD COLUMN signature_scheme text NOT NULL DEFAULT 'none' "
       "CHECK (signature_scheme IN ('none', 'ed25519'))")
    _q("ALTER TABLE tb_contract_event ADD COLUMN signer_key_ref text")
    _q("ALTER TABLE tb_contract_event ADD CONSTRAINT ck_event_signature CHECK ("
       "(signature_scheme = 'none') = (signature IS NULL AND signer_key_ref IS NULL) "
       "AND (signature_scheme = 'none' OR event_type IN ('CONFIRMED', 'DISPUTED')))")
    _q("""CREATE FUNCTION tb_contract_event_signer_check() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        BEGIN
          IF NEW.signature_scheme <> 'none' AND NOT EXISTS (
               SELECT 1 FROM party_signing_key k WHERE k.key_ref = NEW.signer_key_ref
               AND k.company_id = NEW.company_id AND k.status = 'ACTIVE' AND k.scheme = NEW.signature_scheme) THEN
            RAISE EXCEPTION 'SIGNER_KEY_NOT_ACTIVE: % is not an active key of %', NEW.signer_key_ref, NEW.company_id
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER tb_contract_event_signer_check BEFORE INSERT ON tb_contract_event "
       "FOR EACH ROW EXECUTE FUNCTION tb_contract_event_signer_check()")

    # ── assert rather than trust ────────────────────────────────────────────
    assert conn.execute(sa.text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                                "WHERE relname = 'party_signing_key'")).scalar(), "party_signing_key not FORCED"
    held = set(conn.execute(sa.text("SELECT privilege_type FROM information_schema.role_table_grants "
                                    "WHERE grantee = 'gex_app' AND table_name = 'party_signing_key'")).scalars())
    assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on party_signing_key"
    cols = set(conn.execute(sa.text("SELECT column_name FROM information_schema.column_privileges "
                                    "WHERE grantee = 'gex_app' AND table_name = 'party_signing_key' "
                                    "AND privilege_type = 'UPDATE'")).scalars())
    assert cols == set(LIFECYCLE), f"gex_app may update {sorted(cols)}"


def downgrade() -> None:
    n = _q("SELECT count(*) FROM tb_contract_event WHERE signature_scheme <> 'none'").scalar()
    assert n == 0, f"{n} contract event(s) carry a party's signature; refusing to drop it"
    _q("DROP TRIGGER IF EXISTS tb_contract_event_signer_check ON tb_contract_event")
    _q("DROP FUNCTION IF EXISTS tb_contract_event_signer_check()")
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT IF EXISTS ck_event_signature")
    for col in ("signer_key_ref", "signature_scheme", "signature"):
        _q(f"ALTER TABLE tb_contract_event DROP COLUMN IF EXISTS {col}")
    _q("DROP FUNCTION IF EXISTS app_party_signing_key(text)")
    _q("DROP TABLE IF EXISTS party_signing_key")
    _q("DROP FUNCTION IF EXISTS party_signing_key_guard()")
