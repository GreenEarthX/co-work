import { describe, it, expect } from 'vitest';
import { resolveActionRoute } from '../actionRouter';

// Behaviour-preservation contract for the resolver that replaced the inline
// F4 logic in ProducerBankabilityView. These assertions ARE the F1–F5 fixes,
// now enforced in one place instead of scattered across screens.

const PRODUCER = { business_function: 'ENGINEERING' as const };
const FINANCE = { business_function: 'FINANCE_TREASURY' as const };
const EXEC = { business_function: 'EXECUTIVE' as const };
const BANK = { business_function: 'COMMERCIAL' as const, service_type: 'BANK' as const };

const PID = 'proj_x';

describe('resolveActionRoute', () => {
  it('ALLOWED: an open route resolves and substitutes {project_id}', () => {
    const r = resolveActionRoute(PRODUCER, {
      kind: 'evidence:curtailment_assessment',
      preferred_route: '/projects/{project_id}/edit',
      owner_function: 'ENGINEERING',
    }, PID);
    expect(r.status).toBe('allowed');
    expect(r.route).toBe('/projects/proj_x/edit');
  });

  it('FORBIDDEN: finance-guarded route + producer → no route, owner named (the F4 case)', () => {
    // ppa_tenor_debt_comparison routes to /dscr-sensitivity (FinanceRouteGuard).
    const r = resolveActionRoute(PRODUCER, {
      kind: 'evidence:ppa_tenor_debt_comparison',
      preferred_route: '/dscr-sensitivity',
      owner_function: 'FINANCE_TREASURY',
    }, PID);
    expect(r.status).toBe('forbidden');
    expect(r.route).toBeNull();             // never hand back a route the viewer bounces off
    expect(r.reason).toMatch(/FINANCE_TREASURY/);
  });

  it('ALLOWED: same finance-guarded route for FINANCE / EXEC / BANK', () => {
    for (const u of [FINANCE, EXEC, BANK]) {
      const r = resolveActionRoute(u, {
        kind: 'evidence:ppa_tenor_debt_comparison',
        preferred_route: '/dscr-sensitivity',
        owner_function: 'FINANCE_TREASURY',
      }, PID);
      expect(r.status).toBe('allowed');
      expect(r.route).toBe('/dscr-sensitivity');
    }
  });

  it('FALLBACK: guarded preferred + open fallback → routes to fallback, names owner', () => {
    const r = resolveActionRoute(PRODUCER, {
      kind: 'risk:financing',
      preferred_route: '/dscr-sensitivity',     // guarded for producer
      fallback_route: '/bankability-scores',    // open
      owner_function: 'FINANCE_TREASURY',
    }, PID);
    expect(r.status).toBe('fallback');
    expect(r.route).toBe('/bankability-scores');
    expect(r.owner_function).toBe('FINANCE_TREASURY');
  });

  it('FORBIDDEN: no preferred route at all → read-only, never a bogus link', () => {
    const r = resolveActionRoute(PRODUCER, { kind: 'x', owner_function: 'LEGAL' }, PID);
    expect(r.status).toBe('forbidden');
    expect(r.route).toBeNull();
  });
});

// Step 2 — workflow-locked OWNER SURFACES (offtake-quality / capital-stack).
// Anyone may navigate there, but only the owner acts; non-owners are routed to
// the universal fallback (the F3 fix, now decided centrally by the resolver).
describe('resolveActionRoute · owner surfaces (risk-flag ways)', () => {
  const COMMERCIAL = { business_function: 'COMMERCIAL' as const };
  const OFFTAKER = { business_function: 'COMMERCIAL' as const, company_type: 'OFFTAKER' };

  it('offtake: COMMERCIAL owns /offtake-quality → allowed there', () => {
    const r = resolveActionRoute(COMMERCIAL, {
      kind: 'risk:offtake', preferred_route: '/offtake-quality', owner_function: 'COMMERCIAL',
      fallback_route: '/producer-bankability?project=p&gate=G4',
    }, PID);
    expect(r.status).toBe('allowed');
    expect(r.route).toBe('/offtake-quality');
  });

  it('offtake: PRODUCER is NOT the owner → routed to the gate-evidence fallback, not the locked screen', () => {
    const r = resolveActionRoute(PRODUCER, {
      kind: 'risk:offtake', preferred_route: '/offtake-quality', owner_function: 'COMMERCIAL',
      fallback_route: '/producer-bankability?project=p&gate=G4',
    }, PID);
    expect(r.status).toBe('fallback');
    expect(r.route).toContain('/producer-bankability');
  });

  it('financing: FINANCE owns /capital-stack; PRODUCER falls back to the open scoreboard', () => {
    const fin = resolveActionRoute(FINANCE, {
      kind: 'risk:financing', preferred_route: '/capital-stack', owner_function: 'FINANCE_TREASURY',
      fallback_route: '/bankability-scores',
    }, PID);
    expect(fin.status).toBe('allowed');
    expect(fin.route).toBe('/capital-stack');

    const prod = resolveActionRoute(PRODUCER, {
      kind: 'risk:financing', preferred_route: '/capital-stack', owner_function: 'FINANCE_TREASURY',
      fallback_route: '/bankability-scores',
    }, PID);
    expect(prod.status).toBe('fallback');
    expect(prod.route).toBe('/bankability-scores');
  });

  it('offtaker company_type also owns offtake-quality', () => {
    const r = resolveActionRoute(OFFTAKER, {
      kind: 'risk:offtake', preferred_route: '/offtake-quality', owner_function: 'COMMERCIAL',
      fallback_route: '/producer-bankability?project=p&gate=G4',
    }, PID);
    expect(r.status).toBe('allowed');
  });
});
