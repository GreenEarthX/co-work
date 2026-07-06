// Screen: lib helper (no screen)
/**
 * Deterministic project narrative renderer.
 * Source of truth = structured fields on CustomerProject.
 * Output = the prose that appears on ProjectProfilePage's DESCRIPTION/NARRATIVE block.
 *
 * Doctrine:
 *  - Every clause traces back to exactly one structured field path.
 *  - If a field is missing, the clause is omitted — never invented.
 *  - The function is pure: same project → same string, always.
 *  - Editing the prose is disabled; users edit fields, which re-renders the prose.
 */

import type { CustomerProject, Offtake, CertificationProgress, Incentive } from '@/data/customerProjects';

// ── Public types ─────────────────────────────────────────────────────────────

export interface NarrativeClause {
  /** Field path(s) on CustomerProject this clause draws from — for the lineage panel. */
  sources: string[];
  /** Rendered text (no trailing whitespace, no terminal punctuation — composer adds it). */
  text: string;
}

export interface RenderedNarrative {
  text: string;                 // full narrative string
  clauses: NarrativeClause[];   // ordered list of clause → source mappings
  missing_fields: string[];     // field paths absent on the project
}

// ── Clause renderers ─────────────────────────────────────────────────────────

function ktYr(p: CustomerProject): number | null {
  if (typeof p.capacity_kt_yr === 'number') return p.capacity_kt_yr;
  if (typeof p.capacity_mtpd === 'number') {
    // mtpd × 365 / 1000 → kt/yr.  Round to nearest kt.
    return Math.round((p.capacity_mtpd * 365) / 1000);
  }
  return null;
}

function fmtCap(n: number): string {
  // 120 → "120,000".  We keep kt in the variable, render t/yr in the prose for industry idiom.
  return (n * 1000).toLocaleString('en-US');
}

function flowClause(p: CustomerProject): NarrativeClause | null {
  const parts: string[] = [];
  const sources: string[] = [];
  if (p.energy_input) {
    parts.push(`${p.energy_input.power_mw} MW ${p.energy_input.source}`);
    sources.push('energy_input.power_mw', 'energy_input.source');
  }
  if (p.electrolyser) {
    parts.push(`${p.electrolyser.capacity_mw} MW ${p.electrolyser.technology} electrolysis`);
    sources.push('electrolyser.capacity_mw', 'electrolyser.technology');
  }
  const kt = ktYr(p);
  if (kt != null) {
    parts.push(`${fmtCap(kt)} t/yr ${p.molecule}`);
    sources.push(p.capacity_kt_yr != null ? 'capacity_kt_yr' : 'capacity_mtpd', 'molecule');
  }
  if (parts.length === 0) return null;
  return { sources, text: parts.join(' → ') };
}

function offtakePriority(o: Offtake): number {
  // Lower = higher priority for narrative ordering.
  switch (o.binding_status) {
    case 'BINDING':    return 0;
    case 'TERM_SHEET': return 1;
    case 'LOI':        return 2;
    case 'MOU':        return 3;
    case 'INDICATIVE': return 4;
    default:           return 5;
  }
}

function offtakeRoleLabel(rank: number): string {
  if (rank === 0) return 'Primary offtake';
  if (rank === 1) return 'Secondary';
  return 'Indicative';
}

function offtakeDetail(o: Offtake): string {
  const bits: string[] = [];
  if (o.binding_status === 'BINDING') {
    const term = o.term_years ? `${o.term_years}-year ` : '';
    const price = o.price_type === 'FIXED' ? 'fixed-price' : o.price_type === 'INDEX_LINKED' ? 'index-linked' : '';
    const from  = o.delivery_start ? ` from ${new Date(o.delivery_start).getUTCFullYear()}` : '';
    const head  = [`binding`, term + price].filter(Boolean).join(' ').trim();
    bits.push(`${head}${from}`);
    if (o.notes?.toLowerCase().includes('bankable')) bits.push('bankable contract');
  } else {
    if (o.term_years) bits.push(`${o.term_years}-year ToP`);
    if (o.volume_tpy) bits.push(`${o.volume_tpy.toLocaleString('en-US')} t/yr`);
    if (o.is_related_party) bits.push('related-party');
    if (o.verification === 'UNVERIFIED') bits.push('unverified');
    else if (o.binding_status === 'INDICATIVE') bits.push('non-binding');
  }
  return bits.join(', ');
}

function offtakesClauses(p: CustomerProject): NarrativeClause[] {
  if (!p.offtakes || p.offtakes.length === 0) return [];
  const ranked = [...p.offtakes].sort((a, b) => offtakePriority(a) - offtakePriority(b));
  return ranked.slice(0, 3).map((o, i) => ({
    sources: [`offtakes[${p.offtakes!.indexOf(o)}]`],
    text: `${offtakeRoleLabel(i)}: ${o.party} (${offtakeDetail(o)})`,
  }));
}

function certName(c: CertificationProgress): string {
  switch (c.scheme) {
    case '45V':              return '45V';
    case 'RFNBO':            return 'RFNBO';
    case 'GoO':              return 'GoO';
    case 'ISCC':             return 'ISCC';
    case 'FuelEU_Maritime':  return 'FuelEU Maritime';
    case 'CORSIA':           return 'CORSIA';
    case 'ASTM_D7566':       return 'ASTM D7566';
    case 'RED_III':          return 'RED III';
    default:                 return c.scheme;
  }
}

function certPhrase(c: CertificationProgress): string {
  const head = certName(c);
  switch (c.status) {
    case 'ACTIVE':         return `${head} active${c.tier ? ` (${c.tier} pathway)` : ''}`;
    case 'UNDER_REVIEW':   return `${head} under ${c.note ?? 'review'}`;
    case 'PRE-ASSESSMENT': return `${head} in pre-assessment`;
    case 'INTENDED':       return `${head} targeted`;
    case 'WITHDRAWN':      return `${head} withdrawn`;
    default:               return head;
  }
}

function certificationsClause(p: CustomerProject): NarrativeClause | null {
  if (!p.certifications || p.certifications.length === 0) return null;
  const phrases = p.certifications.map(certPhrase).join(', ');
  return {
    sources: p.certifications.map((_, i) => `certifications[${i}]`),
    text: `Certification: ${phrases}`,
  };
}

function incentiveAmount(i: Incentive): string {
  if (typeof i.amount_usd === 'number') {
    if (i.amount_usd >= 1_000_000_000) return `$${(i.amount_usd / 1_000_000_000).toFixed(1).replace(/\.0$/, '')}B`;
    if (i.amount_usd >= 1_000_000)     return `$${Math.round(i.amount_usd / 1_000_000)}M`;
    return `$${i.amount_usd.toLocaleString('en-US')}`;
  }
  if (typeof i.amount_eur === 'number') {
    if (i.amount_eur >= 1_000_000_000) return `€${(i.amount_eur / 1_000_000_000).toFixed(1).replace(/\.0$/, '')}B`;
    if (i.amount_eur >= 1_000_000)     return `€${Math.round(i.amount_eur / 1_000_000)}M`;
    return `€${i.amount_eur.toLocaleString('en-US')}`;
  }
  return '';
}

function incentiveLabel(kind: Incentive['kind']): string {
  switch (kind) {
    case 'IRA_45V':              return 'IRA 45V';
    case 'IRA_45Q':              return 'IRA 45Q';
    case 'IRA_GRANT':            return 'IRA grant';
    case 'EU_INNOVATION_FUND':   return 'EU Innovation Fund';
    case 'EU_HYDROGEN_BANK':     return 'EU Hydrogen Bank';
    case 'BPIFRANCE':            return 'Bpifrance';
    case 'KFW_GRANT':            return 'KfW grant';
    case 'DOE_LPO':              return 'DOE LPO';
    default:                     return 'incentive';
  }
}

function incentivesClause(p: CustomerProject): NarrativeClause | null {
  if (!p.incentives || p.incentives.length === 0) return null;
  // Aggregate by US programs (IRA bucket) for the legacy "IRA incentives: ~$X secured" phrasing.
  const secured = p.incentives.filter(i => i.status === 'SECURED');
  if (secured.length === 0) return null;
  const allIra = secured.every(i => i.kind.startsWith('IRA_'));
  if (allIra) {
    // Sum USD amounts when present.
    const totalUsd = secured.reduce((s, i) => s + (i.amount_usd ?? 0), 0);
    const amt = totalUsd > 0 ? incentiveAmount({ ...secured[0], amount_usd: totalUsd, amount_eur: null }) : '';
    return {
      sources: secured.map((_, i) => `incentives[${i}]`),
      text: `IRA incentives: ${amt ? `~${amt} ` : ''}secured`,
    };
  }
  const items = secured.map(i => `${incentiveLabel(i.kind)}${incentiveAmount(i) ? ` ${incentiveAmount(i)}` : ''}`);
  return {
    sources: secured.map((_, i) => `incentives[${i}]`),
    text: `Incentives: ${items.join(', ')}`,
  };
}

function timelineClause(p: CustomerProject): NarrativeClause | null {
  const t = p.timeline;
  if (!t || (t.construction_start_year == null && t.production_start_year == null)) return null;
  const parts: string[] = [];
  const sources: string[] = [];
  if (t.construction_start_year) {
    parts.push(`Construction start ${t.construction_start_year}`);
    sources.push('timeline.construction_start_year');
  }
  if (t.production_start_year) {
    parts.push(`production ${t.production_start_year}`);
    sources.push('timeline.production_start_year');
  }
  return { sources, text: parts.join(', ') };
}

// ── Public renderer ──────────────────────────────────────────────────────────

const REQUIRED_FIELD_PATHS = [
  'energy_input.power_mw',
  'energy_input.source',
  'electrolyser.capacity_mw',
  'electrolyser.technology',
  'capacity_kt_yr',
  'offtakes',
  'certifications',
  'incentives',
  'timeline.construction_start_year',
  'timeline.production_start_year',
];

function readPath(obj: any, path: string): unknown {
  return path.split('.').reduce<any>((acc, k) => (acc == null ? acc : acc[k]), obj);
}

export function renderNarrative(project: CustomerProject): RenderedNarrative {
  const clauses: NarrativeClause[] = [];
  const flow = flowClause(project);                    if (flow) clauses.push(flow);
  const ots  = offtakesClauses(project);               clauses.push(...ots);
  const cert = certificationsClause(project);          if (cert) clauses.push(cert);
  const inc  = incentivesClause(project);              if (inc)  clauses.push(inc);
  const tl   = timelineClause(project);                if (tl)   clauses.push(tl);

  const text = clauses.map(c => c.text).join('. ') + (clauses.length ? '.' : '');

  const missing_fields = REQUIRED_FIELD_PATHS.filter(path => {
    const v = readPath(project, path);
    if (Array.isArray(v)) return v.length === 0;
    return v == null;
  });

  return { text, clauses, missing_fields };
}
