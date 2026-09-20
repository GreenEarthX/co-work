#!/usr/bin/env node
/**
 * audit-supabase — fail the build if Supabase data access reappears.
 *
 * WHY
 * ---
 * Measured 2026-09-19: every table behind the frontend's `supabase.from()`
 * calls answered an anonymous request, because the anon key that authorises
 * them ships in the bundle. Increments 1–4 of
 * `docs/supabase-cutover-endpoints.md` moved all of it behind the backend.
 *
 * That kind of change grows back one convenient call at a time. This gate
 * exists so the next `supabase.from("…")` fails CI instead of shipping.
 *
 * NOTHING IS ALLOWED ANY MORE
 * ---------------------------
 * Increment 5 removed the last two callers (the realtime hooks) and the
 * client itself, so the allowlist is empty and the `@supabase/supabase-js`
 * dependency is gone. This gate now answers a simpler question: has anybody
 * put it back?
 *
 *   node scripts/audit-supabase.mjs --check
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("../src", import.meta.url).pathname;

// Files permitted to reach Supabase directly.
//
// EMPTY, as of increment 5 on 2026-09-20 — the client itself is deleted and
// there is no Supabase dependency left in the frontend. Adding an entry here
// means re-introducing a data path that bypasses the backend's ownership and
// entitlement checks, so an entry needs a reason in the commit message, not
// just in this comment.
const ALLOWLIST = new Map([]);

// Data access, not the module's existence. `channel()` is matched too so the
// allowlist has to name the realtime files rather than them slipping by.
const FORBIDDEN = [
  { pattern: /\bsupabase\s*\.\s*from\s*\(/, what: "supabase.from(" },
  { pattern: /\.\s*storage\s*\.\s*from\s*\(/, what: ".storage.from(" },
  { pattern: /\bsupabase\s*\.\s*channel\s*\(/, what: "supabase.channel(" },
  { pattern: /\bsupabase\s*\.\s*rpc\s*\(/, what: "supabase.rpc(" },
];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (/\.(ts|tsx)$/.test(full)) yield full;
  }
}

const violations = [];
const usedAllowances = new Set();

for (const file of walk(ROOT)) {
  const rel = relative(ROOT, file);
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    // Comments describing the old code are not the old code.
    const code = line.replace(/\/\/.*$/, "").replace(/^\s*\*.*$/, "");
    for (const { pattern, what } of FORBIDDEN) {
      if (!pattern.test(code)) continue;
      if (ALLOWLIST.has(rel)) { usedAllowances.add(rel); continue; }
      violations.push({ rel, line: i + 1, what, text: line.trim() });
    }
  });
}

const stale = [...ALLOWLIST.keys()].filter((f) => !usedAllowances.has(f)
  && f !== "lib/backendClient.ts");

if (violations.length) {
  console.error("\n❌ FAIL — direct Supabase data access outside the allowlist:\n");
  for (const v of violations) {
    console.error(`   ${v.rel}:${v.line}  ${v.what}`);
    console.error(`      ${v.text}`);
  }
  console.error("\nThese belong behind the backend. See docs/supabase-cutover-endpoints.md.\n");
  process.exit(1);
}

if (stale.length) {
  console.log(`⚠️  allowlist entries no longer needed (remove them): ${stale.join(", ")}`);
}
console.log(ALLOWLIST.size === 0
  ? "✅ PASS — no Supabase data access anywhere in the frontend."
  : `✅ PASS — no Supabase data access outside ${ALLOWLIST.size} allowed file(s).`);
