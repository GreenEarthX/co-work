# Reusable prompt — publish GEX to GitHub and Docker Hub

Paste this whole block as your message when you want the latest local work
pushed to both `github.com/GreenEarthX/co-work` and Docker Hub (`jmlamay/gex-*`).

---

Push the latest GEX modifications to GitHub and Docker Hub. Follow this
procedure — do not skip steps even if a prior session already ran them, and do
not report anything as pushed until you've verified it against GitHub's API or
Docker Hub's registry, not just local git/docker state.

**0. Check memory for open security or safety flags first.** Before touching
git or Docker, check whether any project memory describes an unresolved
incident, a pending confirmation, or a "prepared but not pushed" state (search
for words like "incident", "compromise", "staged", "not pushed", "pending
approval"). If one exists, stop and surface it — don't proceed with a routine
push until it's addressed or I've explicitly told you to defer it.

**1. Verify current state, don't assume it.**
- `docker info` — confirm the daemon is actually up.
- In `files/co-work`: `git fetch origin`, then compare local `main` to
  `origin/main`. If they've diverged, stop and diagnose before doing anything
  — don't rebase or force-push on assumption.
- Dry-run the sync (`rsync -rn --delete ...`) against both `gex-platform-enhanced`
  and `gex_pf_engine` to see what's actually pending before claiming there's
  nothing to do, or before claiming a large change set is expected.

**2. Sync and review before staging.**
- Run `sync-to-docker.sh` and the same rsync into `co-work/`.
- `git diff --cached --stat` after `git add -A` — actually read the file list.
  If it's wider than the change you intended, that's not automatically wrong
  (another session may have left real, finished work in the tree) — but say so
  explicitly rather than silently committing everything.
- Scan for anything that shouldn't be published: `.env`, `.db`, credentials,
  and anything that looks like an operational artifact (backup dumps, migration
  logs, run logs) rather than source. If you find a credential-shaped string,
  check whether it matches a known public dev-default before treating it as a
  real leak — but exclude operational-artifact directories regardless of
  whether they contain secrets; they don't belong in the repo either way.
- Check every `.gitignore` rule you rely on actually matches with
  `git check-ignore -v <path>` — a rule with a slash in the middle is anchored
  to the repo root and won't match a nested path with the same name.

**3. Verify before committing, not after.**
- If backend or pf_engine route/core files changed, confirm the app still
  imports: `docker run --rm <image> python -c "import app.main"` (or
  `pf_engine.main`), overlaying current source with `-v .../app:/app/app:ro` if
  you don't want to rebuild yet. A clean import with a route count printed is
  the bar — a traceback means do not commit.
- If `requirements.txt` changed, that overlay test isn't valid anymore — you
  need a real rebuild before it means anything.

**4. Commit and push to GitHub.**
- Write a commit message that states what changed, why, and what you verified
  — not just a summary of the diff.
- `git push origin main`, then confirm independently:
  `git log --oneline --branches --not --remotes=origin` (must be empty) AND
  a `curl` to `api.github.com/repos/<org>/<repo>/commits/main` matching your
  local HEAD. Don't trust git's own "everything up-to-date" as the only signal.

**5. Build, smoke-test, and push Docker images.**
- Pick the version bump (patch/minor/major) based on what actually changed.
- Rebuild only the images whose source changed — check with
  `git diff <old>..<new> --stat -- <project>/` before deciding to retag instead
  of rebuild.
- Smoke-test every image you built *before* pushing:
  `docker run --rm <image> python -c "import <entrypoint module>"` for Python
  services. A crash here has broken every release that skipped this step.
- Tag `latest` alongside the version tag, then push all six tags (or however
  many services × 2 tags apply).

**6. Run the clean pull test — this is not optional, but NEVER use `down -v`.**
- `gex-demo-compose.yml`'s `postgres_data` volume is not disposable test
  state — it is the one real GEX database, the same one the project's own
  CLAUDE.md documents being lost and painstakingly restored multiple times.
  `docker compose down -v` deletes every volume the file declares, postgres
  included, with no prompt and no way back except the last backup. **This
  caused a real data-loss incident on 2026-10-20** (and plausibly the two
  earlier ones the project's own notes couldn't explain the cause of) before
  this line was rewritten. Do not reintroduce `-v` here under any framing —
  not "just to be thorough," not "to be sure the pull is clean."
- The safe sequence, which only touches the three GEX-built images and their
  containers:
  ```
  docker compose -f gex-demo-compose.yml stop backend frontend pf_engine
  docker compose -f gex-demo-compose.yml rm -f backend frontend pf_engine
  docker rmi -f $(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^jmlamay/gex-")
  docker compose -f gex-demo-compose.yml pull
  docker compose -f gex-demo-compose.yml up -d
  ```
  `postgres` and `redis` are never stopped, removed, or touched — the GEX
  images are what changed, so only they need re-pulling.
- Poll for readiness (backend/finance-engine style services can take up to a
  minute on first import) rather than declaring failure early.
- Check every service, not just the one that's easiest to check from a browser
  — including any secondary engine/microservice the main backend depends on.
  Test with a real authenticated request against at least one endpoint that
  actually changed in this release, not just a generic health check.
- If Docker Desktop crashes mid-test (it has, more than once on this machine),
  restart it and actually re-run the step that was in flight — don't assume a
  command that ran before a crash completed successfully.
- If a database-affecting command is ever genuinely necessary (a schema
  change, a role reset), that is a deliberate, separate decision — surface it
  and get explicit confirmation before running anything that could remove or
  reinitialize `postgres_data`. It is never a routine part of a release push.

**7. Update the colleague-facing file.**
- `gex-demo-compose.yml` image tags must match what you just pushed — this is
  what other people actually run, and forgetting it means they stay on a
  possibly-broken older version.

**8. Report accurately.**
- State what was actually verified (API-confirmed, registry-confirmed) versus
  what you're inferring.
- If you excluded anything from the push, or found something that wasn't part
  of the original ask (extra pending work, a security concern, a broken
  gitignore rule), say so plainly rather than folding it silently into "done."
- If you find something that needs my explicit approval before it can proceed
  (a destructive git operation, a public disclosure, anything touching shared
  history other people may have pulled), stop and ask — don't treat a general
  "push it" as authorization for that specific step.

---

*This procedure exists because every one of its steps has caught a real
problem at least once: a broken build, a crash-looping service, a diverged
branch, a leaked-looking credential that turned out to be a known dev default,
a gitignore rule that silently didn't match, and a supply-chain compromise
sitting undiscovered in commit history. Skipping a step doesn't save time if
it ships the next one of these.*
