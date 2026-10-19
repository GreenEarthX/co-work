import os, sys, json, sqlite3
S = sys.argv[1]
from app.core.config import settings
for n in type(settings).model_fields:
    if n.endswith("_DB_BACKEND"):
        os.environ[n] = "sqlite"; setattr(settings, n, "sqlite")
settings.SQLITE_DB_PATH = f"{S}/cb_baseline.db"
import app.api.v1.capital_bridge as cb
cb.init_db()
c = sqlite3.connect(settings.SQLITE_DB_PATH)
tbls = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
if "projects" not in tbls:
    c.execute("create table projects (project_id text primary key, name text, owner_id text, company_id text)")
c.execute("insert or ignore into projects (project_id, name) values ('baseline_h2','baseline H2 50MW')"); c.commit(); c.close()
_gens = []
def db():
    g = cb.get_db(); _gens.append(g); return next(g)
cb.bootstrap_from_fuel("baseline_h2", fuel_type=cb.FuelType("H2"), nameplate_mw=50.0, fel_1_year=2026, owner_user_id=None, company_id=None, db=db())
cb.bootstrap_capital_stack("baseline_h2", total_capex_eur=100_000_000.0, db=db())
r = cb.compute_capital_bridge("baseline_h2", db=db())
d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
d.pop("computed_at", None)
json.dump(d, open(f"{S}/baseline_capital_bridge_h2_50mw.json","w"), indent=2, default=str, sort_keys=True)
json.dump(cb.FUEL_DEFAULTS, open(f"{S}/baseline_fuel_defaults.json","w"), indent=2, default=str, sort_keys=True)
print(json.dumps(d, indent=1, default=str)[:2500])
