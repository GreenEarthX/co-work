// Screen: Gates & Evidence — "Who verifies" panel.
// Everyone on the project sees which independent reviewer verifies which gates.
// GEX staff appoint and revoke here, on the instruction of a named party
// (owner decision 2026-10-21). The server decides who is GEX staff (can_appoint).
import { type ChangeEvent, useCallback, useEffect, useState } from "react";
import { reviewersAPI, type ProjectReviewers } from "@/lib/api";

const ROLE_LABEL: Record<string, string> = {
  CERTIFIER: "Certifier",
  INDEPENDENT_ENGINEER: "Independent engineer",
  LENDERS_ADVISER: "Lenders' adviser",
  INSURER: "Insurer",
  GRANT_ASSESSOR: "Grant body's assessor",
  SEED_INVESTOR_ADVISER: "Seed investor's adviser",
  STRATEGIC_INVESTOR_ADVISER: "Strategic investor's adviser",
};

async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
}

export function ReviewersPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<ProjectReviewers | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ user_id: "", role: "", instructed_by: "" });
  const [doc, setDoc] = useState<{ name: string; sha: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await reviewersAPI.list(projectId));
    } catch (err: any) {
      setData(null);
      setError(err?.message || "Could not load reviewers");
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const pickDoc = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    setDoc(file ? { name: file.name, sha: await sha256Hex(file) } : null);
  };

  const appoint = async () => {
    if (!doc) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await reviewersAPI.appoint(projectId, { ...form, instruction_sha256: doc.sha });
      setNotice(`Appointed ${form.user_id}. It takes effect at their next sign-in.`);
      setForm({ user_id: "", role: "", instructed_by: "" });
      setDoc(null);
      await load();
    } catch (err: any) {
      setError(err?.message || "Appointment refused");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (userId: string, role: string) => {
    const reason = window.prompt(`Reason for revoking ${userId} as ${ROLE_LABEL[role] || role}?`);
    if (!reason || reason.trim().length < 3) return;
    setError(null);
    setNotice(null);
    try {
      await reviewersAPI.revoke(projectId, userId, role, reason.trim());
      setNotice(`Revoked ${userId}. It takes effect at their next sign-in.`);
      await load();
    } catch (err: any) {
      setError(err?.message || "Revocation refused");
    }
  };

  if (!projectId) return null;
  const reviewers = data?.reviewers ?? [];
  const canSubmit = form.user_id.trim() && form.role && form.instructed_by.trim() && doc && !busy;

  return (
    <section className="mt-6 rounded-lg border border-slate-200 bg-white p-4" aria-label="Who verifies">
      <h2 className="text-sm font-semibold text-slate-900">Who verifies</h2>
      <p className="mt-1 text-xs text-slate-600">
        Evidence counts only when an independent reviewer appointed to the project verifies it: never the
        submitter, its company, the project owner, or GEX.
      </p>

      {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="mt-2 text-xs text-green-700">{notice}</p>}

      {data && reviewers.length === 0 && (
        <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          No reviewer is appointed yet, so no evidence on this project can be verified. GEX appoints reviewers on
          the instruction of the lender, grant body, investor or insurer whose decision relies on the gate.
        </p>
      )}

      {reviewers.length > 0 && (
        <table className="mt-3 w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="py-1 pr-2 font-medium">Reviewer</th>
              <th className="py-1 pr-2 font-medium">Company</th>
              <th className="py-1 pr-2 font-medium">Role</th>
              <th className="py-1 pr-2 font-medium">Verifies</th>
              {data?.can_appoint && <th className="py-1" />}
            </tr>
          </thead>
          <tbody>
            {reviewers.map(r => (
              <tr key={`${r.user_id}-${r.role}`} className="border-t border-slate-100">
                <td className="py-1 pr-2 text-slate-900">{r.user_name}</td>
                <td className="py-1 pr-2 text-slate-700">{r.company_name}</td>
                <td className="py-1 pr-2 text-slate-700">{ROLE_LABEL[r.role] || r.role}</td>
                <td className="py-1 pr-2 font-mono text-slate-700">{r.gates.join(", ")}</td>
                {data?.can_appoint && (
                  <td className="py-1 text-right">
                    <button onClick={() => revoke(r.user_id, r.role)}
                      className="rounded border border-red-300 px-2 py-0.5 text-red-700 hover:bg-red-50">
                      Revoke
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data?.can_appoint && (
        <div className="mt-4 rounded border border-slate-200 bg-slate-50 p-3">
          <div className="text-xs font-semibold text-slate-800">Appoint a reviewer (GEX staff)</div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <label className="text-xs text-slate-700">Account id
              <input value={form.user_id} onChange={e => setForm({ ...form, user_id: e.target.value })}
                className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1" placeholder="e.g. anna_ie_firm_com" />
            </label>
            <label className="text-xs text-slate-700">Role
              <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}
                className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1">
                <option value="">Choose…</option>
                {Object.entries(data.roles).map(([role, gates]) => (
                  <option key={role} value={role}>{ROLE_LABEL[role] || role} — {gates.join(", ")}</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-slate-700">Instructed by
              <input value={form.instructed_by} onChange={e => setForm({ ...form, instructed_by: e.target.value })}
                className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                placeholder="The lender, grant body, investor or insurer" />
            </label>
            <label className="text-xs text-slate-700">Instruction document
              <input type="file" onChange={pickDoc} className="mt-0.5 w-full text-xs" />
              {doc && <span className="mt-0.5 block font-mono text-[10px] text-slate-500">{doc.name} · sha256 {doc.sha.slice(0, 16)}…</span>}
            </label>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">
            The document is hashed in your browser and only its sha256 is recorded. The project owner cannot instruct
            its own verifier, and no GEX account can be appointed.
          </p>
          <button onClick={appoint} disabled={!canSubmit}
            className={`mt-2 rounded px-3 py-1 text-xs font-semibold ${canSubmit
              ? "bg-slate-950 text-white hover:bg-slate-800" : "cursor-not-allowed bg-slate-200 text-slate-400"}`}>
            {busy ? "Appointing…" : "Appoint"}
          </button>
        </div>
      )}
    </section>
  );
}
