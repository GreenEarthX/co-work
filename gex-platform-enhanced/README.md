# GreenEarthX (GEX) platform

GEX takes green-fuel projects (hydrogen, ammonia, e-methanol, SAF and biofuels) from
concept to committed capital and then to traded, delivered product. It keeps one
evidence record per project. Independent reviewers verify it, the PF engine judges
it against twelve bankability gates (G0–G11), and the market, contracts and custody
ledger build on the same record.

**State on 22 Nov 2026:**

| | |
|---|---|
| Branch | `main` |
| Migration head | 129 |
| Evidence rules | 4.9.0 |
| Database | PostgreSQL only: 178 tables, 171 under forced row-level security |
| Platform tests | 2124 pass / 15 skip / 0 fail (21 Nov) |
| Frontend tests | 346 |

Counts move, so re-measure before quoting them.

---

## Services

```text
Browser ──► Frontend :3000  (Vite + React + TypeScript; /api proxied to :8000)
               │
               ▼
          Platform API :8000  (FastAPI) ──► PostgreSQL :55432  (role gex_app, RLS applies)
               │
               ├──► PF engine :8001   gates, project finance, Gabillon  (sibling repo gex_pf_engine)
               └──► TEA engine :8002  techno-economic assessment, OpenPyTEA 3.2.3 (stateless)
```

## Repository layout

| Path | What it is |
|---|---|
| `backend/app/` | Platform API. Routes are in `api/v1/`, rules in `core/`, the contract record in `trading_book/`. |
| `backend/alembic/` | Migrations. Upgrade with `auth_slice@head` (`docs/OPERATIONS.md` §6). |
| `backend/tests/` | Platform tests. Export both database URLs before running. |
| `backend/scripts/` | Operational and one-off data scripts. |
| `frontend/src/` | React app. Navigation is in `config/menuArchitecture.ts`; every API call goes through `lib/fetchAuthBridge` / `api.ts`. |
| `tea_engine/` | TEA service. |
| `deal_engine/` | Deal computation. Dormant: no caller. Not a copy of `gex_pf_engine`. |
| `efuel_truth_stack/` | Event-sourced reference core (in-memory, tests only). |
| `docs/` | See below. |

## Start here

| To… | Read |
|---|---|
| set up a development stack | `docs/SETUP.md` |
| run, back up, restore, migrate, deploy | `docs/OPERATIONS.md` |
| answer a security questionnaire, or prepare the public server | `docs/SECURITY.md` |
| work on the code (agents load this) | `.claude/CLAUDE.md` |
| know the current state, open defects and decisions | `docs/CLAUDE_HANDOFF.md` (§8 known defects, §10 current task, §12 decisions) |
| see the commercial gaps | `docs/COMMERCIAL_PLATFORM_GAP_REGISTER.md` |
| explain the twelve gates to a client | `docs/GEX-12Gates-Multi-Party-Review_Good.docx` |

The documentation audit of 22 Nov 2026 (`files/DOCUMENTATION_AUDIT_2026-11-22.md`,
outside this repository) lists which other documents in `docs/` are current and
which are dated records.

## Rules that are easy to break

- **Never point `DATABASE_URL` at `gex_user`, the superuser.** It switches off tenant isolation.
- **Migrations:** run them with `ALEMBIC_DATABASE_URL` exported, and upgrade to `auth_slice@head`.
- **No SQLite path, and no Supabase.** Do not add either back; guard tests fail if you do.
- **Gate figures come only from the PF engine.** Reference values are approved by a person on the GEX staff console, never by a script.
- **The `co-work` mirror on GitHub is public.** No client data and no real secret go into this tree.

## License

Proprietary — GreenEarthX.
