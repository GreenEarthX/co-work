# GEX Objective-Led Product Pathway

## Thesis

GEX wins when it becomes the fastest way for a serious stakeholder to answer one high-value question:

**Is this project real enough to act on now?**

Everything else is support.

The platform should stop behaving like a navigation system for documents and start behaving like a decision system for capital, risk, supply, and compliance.

## Product Goal

Turn GEX into the operating system for green fuel project decisions:

- one project
- one objective
- one blocking truth
- one next action

## North Star

Within 90 seconds of landing on a project, a user should know:

1. whether the project is ready, conditional, or blocked
2. what the single most important blocker is
3. what action should happen next
4. who owns that action

If GEX cannot do that, the rest of the product is noise.

## The New Product Spine

### 1. Start with the decision, not the menu

Every major entry point should begin with:

**What are you trying to decide today?**

Primary decision lanes:

- Is this project bankable?
- Can I buy this molecule?
- What risk is still uninsured?
- What evidence is missing for approval?

Navigation remains available, but it is not the front door.

### 2. Make readiness the hero metric

Each project should lead with a single readiness state:

- `READY`
- `CONDITIONAL`
- `NOT READY`

That state must be computed from live blockers, not page-level decoration.

### 3. Make molecule context unavoidable

Molecule-specific gating is not a side panel. It is part of the core truth model.

Rules:

- NH3 projects surface HAZOP, Seveso, terminal interface, and specialist liability first
- SAF projects surface process hazard review, ASTM D7566, and offtake certification first
- H2 and e-Methanol get their own top-level gating model, not generic treatment

### 4. Make handoffs first-class product events

The real product is not only evidence. It is cross-functional trust transfer.

Every meaningful handoff should generate a project event:

- insurer sign-off
- offtaker executive approval
- HAZOP completion or delay
- lender commitment change
- workflow promotion or rejection

If the handoff is not captured in-platform, GEX does not own the decision chain.

### 5. Make trust real, not implied

The UX promise is enterprise-grade coordination. That promise only holds if identity, scope, and project visibility are enforced server-side.

Until then, the experience is persuasive but not yet defensible.

## What To Build Next

### Priority 1: Trust Foundation

Objective:
Make every screen and workflow claim operationally true.

Ship:

- real JWT-authenticated session flow
- mounted ABAC middleware on all protected API routes
- project-scoped server enforcement
- role and company resolution from token claims, not browser state

Success metric:
No protected project data can be accessed, inferred, or simulated outside valid server scope.

### Priority 2: Project Truth Layer

Objective:
Make the first screen the most useful screen.

Ship:

- unified project readiness service
- one blocker summary per project
- owner + due date on next action
- live task router fed by real project state, not demo payloads

Success metric:
A banker, insurer, or producer can explain the project state after one screen and one minute.

### Priority 3: Molecule-First Operating Views

Objective:
Make sophisticated stakeholders trust GEX immediately.

Ship:

- H2-specific gate set
- e-Methanol-specific gate set
- molecule-aware evidence hierarchy
- molecule-aware insurance defaults
- molecule-aware decision summaries on home, finance, insurance, and compliance views

Success metric:
A domain expert sees their molecule reflected in the first 30 seconds.

### Priority 4: Cooperation Feed as System Record

Objective:
Make GEX the place where knowledge stops leaking to email.

Ship:

- live event-backed cooperation feed
- workflow history wired to real events
- approval trail embedded in high-stakes actions
- commitment status updates linked to capital items and approvals

Success metric:
A project team can reconstruct who decided what, when, and based on which evidence without leaving the platform.

### Priority 5: Opinionated Exports, Not Export Sprawl

Objective:
Keep exports as outcomes, not destinations.

Ship:

- committee pack from readiness state
- insurer pack from coverage gaps
- buyer pack from supply-fit decision
- evidence-backed export gating

Success metric:
Exports become the final mile of a decision flow, not the main way value is consumed.

## Product Kill List

Reduce or demote anything that behaves like a filing cabinet:

- pages with no decision, no owner, and no next action
- score-first screens with no blocker language
- duplicate routes that fragment the same truth
- “planned” audit surfaces that should already be in the daily workflow

## Operating Principles

- Every page answers a user objective in one sentence.
- Every workflow ends in a decision, not a dashboard.
- Every blocker has an owner.
- Every high-stakes action leaves an event trail.
- Every enterprise promise must be enforced by the backend.

## Final Standard

The product is ready when GEX feels less like software people explore and more like software people rely on.

That is the bar.
