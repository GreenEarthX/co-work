# Gate timing against real transactions, 2022–2026

Researched 2026-09-29. Tests four points where the documents (GREENEARTHX v4.5, Bridge v6) and
the software (evidence rules 4.0.0) disagree, against dated transactions and funder rules.
Labels: [E] documented fact, [P] documented practice, [I] inference.

## Verdicts

| Question | Documents say | Software does | What the transactions show | Verdict |
|---|---|---|---|---|
| When does the offtake bind? | HoT at G4, binding at G10 | G4 needs O4 (binding, with conditions and a longstop); FINANCEABLE needs the offtake **effective** (O5/O7) | In every financed deal sampled, a binding (often conditional) offtake existed **before** credit approval / FID. HoTs are the *entry ticket* for grant auctions (EU Hydrogen Bank: ≥60 % of volume at bid), with binding contracts "expected at financial close". | **Software fits better.** The documents conflate *signing* (early, with CPs) with *effectiveness* (at close), which the software already separates. HoT belongs to an earlier stage than G4. |
| When is insurance bound? | Bound at G7 | G7 = insurability (quotes, market report, exclusions, lender deductibles); bound at G10 | Practice: lenders' insurance consultant reviews the programme during due diligence; placing the insurance is a condition to financial close / first drawdown. No public case found of a full construction programme bound before credit approval. | **Software fits.** Documents should read "insurability at G7, bound at G10". |
| When is senior debt committed? | "Gated behind G10" | G8 unlocks "senior debt commitment", G10 drawdown | Every case has **three** separated stages: credit approval / conditional commitment → definitive signing + CPs (financial close) → drawdown. Months apart; conditional commitments lapse. | **Both half-right.** Software's stages are right, but G8's label overstates: it is a *conditional* commitment. Documents are right that money is only available at G10. |
| Does GEX block? | Bridge v6: "GEX never blocks; visibility, not enforcement" | Gates block (BLOCKED); server refuses invalid evidence | Funders enforce hard gates: CPs, milestone requirements, completion guarantees that are called, termination if contracts are not signed at close. | **Blocking the evidence gate matches how funders work.** Keep: GEX enforces the evidence standard; the funding decision stays with the funder. |

## Offtake timing — dated sequences

| Project | Offtake (form, date) | Debt approval / conditional commitment | Definitive debt / financial close | FID | Reading |
|---|---|---|---|---|---|
| NEOM Green Hydrogen, KSA, ammonia | Air Products exclusive offtaker, long-term take-if-tendered, at JV signing Jul 2020 [E] | — | Financial close 22 May 2023, US$6.1bn non-recourse, 23 banks [E] | = close | Offtake ~3 years before close |
| Stegra, Sweden, green steel | >1.5 Mt pre-sold, announced May 2022 (form not stated) [E]; binding contracts Jun–Jul 2023 (Mercedes-Benz, Scania, Cargill, ZF) [E] | Conditional commitment letters €3.3bn + EIB board approval €750m, 24 Oct 2022, "subject … to completion of final due diligence and documentation" [E]; renewed Jul 2023 [E] | Definitive debt Dec 2023–22 Jan 2024, €4.2bn [E] | — | Early conditional debt can precede binding offtake; definitive debt followed it |
| Atome Villeta, Paraguay, fertiliser | Definitive ≥10-yr binding take-or-pay with Yara, 12 Sep 2025 [E] | IDB Invest board approval US$200m, 19 Nov 2025 [E] | Definitive debt US$420m, 12–13 Mar 2026, availability conditional on equity documents [E] | 23 Apr 2026; first disbursement expected end May 2026 [E] | Offtake → credit approval → signing → FID → drawdown |
| Maersk–Goldwind, China, methanol | 500 kt/yr offtake, 22 Nov 2023 [E] | — | — | Goldwind expected FID *after* executing the offtake, before end-2023 [E] | Offtake → FID |
| Egypt Green Hydrogen (Scatec, Fertiglobe) | 20-yr offtake signed 29 Jun 2024; H2Global award Jul 2024 [E] | EBRD/EIB financing in preparation [E] | Close expected H1 2025; still pending Jan 2026 [E] | pending | Binding offtake necessary, not sufficient |
| Infinium Roadrunner, US, e-SAF | IAG 10-yr offtake announced 17 Feb 2025; American Airlines [E] | — | — | 19 May 2025 [E] | Offtake → FID |
| Twelve AirPlant One, US, e-jet | Alaska + Microsoft purchase commitment 2022, "the commercial signal that made financing and construction possible" [E] | — | US$645m package 2024 [E] | — | Offtake → financing; plant opened 10 Jun 2026 |
| SkyNRG DSL-01, NL, SAF | KLM cost-plus offtake for 75 % in place at close [E] (signing date not public) | — | Financial close 12 Feb 2026, 12-bank syndicate [E] | = close | Offtake in place by close |
| Arcadia ENDOR, Denmark, e-SAF | Uniper: "legally binding", deliveries subject to CPs and COD, 23 Sep 2026 [E] | — | — | targeted Q1 2027 | Binding-with-CPs before FID |
| FlagshipONE, Sweden, e-methanol | No long-term offtake at sustainable pricing [E] | — | — | FID Dec 2022; cancelled 15 Aug 2024 [E] | FID without binding offtake failed |

Market calibration: only about 13 % of contracted clean-hydrogen volumes are backed by fully
binding offtakes (BloombergNEF 2025, cited by OIES ET52) [E]; lenders expect take-or-pay with
creditworthy buyers "typically covering the tenor of the debt plus a tail" (GH2, 2022) [P];
off-take and policy risk "are usually the binding constraints for debt financing, with technology
… more commonly addressed during equity-funded development phases" (OIES ET52) [P].

**What this means for G4 [I].** The documents' "HoT at G4" would let a project reach BUILDABLE on
paper no lender in the sample accepted. HoT-level evidence (O2) is what grant auctions require,
which is a COMMERCIALLY_PLAUSIBLE-stage fact. The documents' "binding at G10" is right in one
sense only: obligations become *unconditional* at close — the software's O5/O7 "effective"
requirement at FINANCEABLE. Stegra is the one partial counter-example: conditional commitment
letters came before binding offtakes, but the renewed approvals and definitive debt came after.

## Funder rules (primary documents)

**EU Hydrogen Bank, IF25 auction** — draft Terms & Conditions and CINEA Q&A v0.2 (3 Feb 2026):
- At application: Heads of Terms or signed pre-contractual term sheets for **≥ 60 %** of hydrogen
  volume; the same for **≥ 60 %** of required electricity (HoTs no older than one year); equity
  support letters for **≥ 60 %** of projected equity; evidence that a grid-connection permit
  application was submitted.
- CINEA, asked whether final binding contracts with off-takers and electrolyser makers are needed
  before grant signature: "No, those contracts are expected at financial close."
- Completion guarantee **8 %** of the maximum grant; financial close within **2.5 years** of grant
  signature; entry into operation within **5 years**; guarantee called and grant terminated if
  requirements are unmet.
- Maritime/aviation topic: terminated if signed contracts for 60 % of volume with maritime
  off-takers are not demonstrated at financial close.
- Electrolysers: at least 75 % must originate in a country **other than China** (stacks included).

These confirm most of the master's §11 (60 % thresholds, 8 %). Two corrections for §11: the
electrolyser rule is *non-China*, not "non-EU"; and §1.4's "8–10 %" should read 8 % (IF25).

**UK SAF Revenue Certainty Mechanism, allocation strategy (Jul 2026):** initial conditions
precedent (e.g. grid connection, planning), milestone requirements (spend or defined commitments),
operational conditions precedent before payments — which "permit the counterparty to withdraw
support if progress stalls and … deter projects submitting speculative bids" [E].

## Debt staging — conditional commitments are not money

| Case | Stage 1: approval / conditional commitment | Stage 2: definitive / close | Stage 3: drawdown / outcome |
|---|---|---|---|
| Stegra | 24 Oct 2022, conditional letters | Dec 2023–Jan 2024 | — |
| Atome | 19 Nov 2025, IDB Invest board | 12–13 Mar 2026, conditional on equity docs | first disbursement expected end May 2026 |
| Plug Power (DOE) | May 2024 | 16 Jan 2025 closed | Nov 2025: activities under the guarantee suspended |
| Montana Renewables (DOE) | 2024 | first tranche ~US$778m Q4 2024; closing announced Jan 2025 | delayed-draw during construction from 2025 |
| Gevo (DOE) | conditional commitment, extended 8 Oct 2025 to 16 Apr 2026 | — | withdrew 15 Apr 2026 |

APMG PPP Guide: "Financial close means not only that the financing documents have been signed,
but also that the prior conditions for the availability of financing have been fulfilled." [P]

## Insurance — practice sources

- Lenders hire an insurance consultant "to review the adequacy of a project's insurance package"
  (Latham & Watkins, *Book of Jargon: Project Finance*) — a due-diligence step, i.e. G7 [P].
- Conditions precedent to the release of funds include "insurance arrangements" (Designing
  Buildings, *Financial close*) [P]; the insurance package is a condition to financial close /
  first drawdown (World Bank PPP insurance checklist, as reported) [P].
- Hydrogen-specific capacity for construction and start-up risks was scarce enough that Marsh
  launched a dedicated facility (up to US$300m per risk, 2022) [E] — why insurability must be
  tested before credit approval.
- Not found: any public hydrogen/e-fuel case with a full construction programme bound before
  credit approval. Early works under a limited notice to proceed may be insured earlier [I].

## Implications for GEX

1. **Documents** — GREENEARTHX §2.3 and §3, Bridge v6 §3 and §9: offtake "binding with conditions
   at G4, effective at G10"; insurance "insurability at G7, bound at G10"; senior debt "credit
   approval / conditional commitment at G8, financial close and drawdown at G10"; replace "GEX never
   blocks" with "GEX enforces the evidence standard; funders decide".
2. **Software (separate task, for decision)** — (a) relabel the G8 capital unlock "Senior debt credit
   approval (conditional)"; (b) consider an explicit O2 checkpoint (HoT for ≥ 60 % of volume) at
   COMMERCIALLY_PLAUSIBLE as a grant-readiness marker, mirroring IF25.
3. **Master §11** — correct "non-EU" → "non-China"; align the guarantee to 8 %; add "binding
   contracts expected at financial close" as the funder's own rule.

## Limits

Public, large, announced deals only; offtake terms are confidential, so the *form* of an offtake is
often known only from the announcing party. Press releases are self-reported. Some dates are
announcement dates, not signing dates. The IF25 document used is the draft T&C plus the official
Q&A; check the final T&C before quoting thresholds to clients.

## Sources

- NEOM financial close (22 May 2023): https://www.prnewswire.com/news-releases/neom-green-hydrogen-company-completes-financial-close-at-a-total-investment-value-of-usd-8-4-billion-in-the-worlds-largest-carbon-free-green-hydrogen-plant-301830653.html
- Air Products, ACWA Power and NEOM agreement (Jul 2020): https://www.airproducts.com/company/news-center/2020/07/0707-air-products-agreement-for-green-ammonia-production-facility-for-export-to-hydrogen-market
- Stegra conditional commitment letters (24 Oct 2022): https://stegra.com/en/news-and-stories/leading-european-financial-institutions-support-h2-green-steels-35-billion-debt-financing
- Stegra definitive debt: https://stegra.com/en/news-and-stories/h2-green-steel-raises-more-than-4-billion-in-debt-financing-for-the-worlds-first-large-scale-green-steel-plant
- Stegra binding offtakes (2023): https://www.hydrogeninsight.com/industrial/h2-green-steel-seals-1-5bn-binding-seven-year-deal-to-supply-hydrogen-based-steel-to-car-technology-firm/2-1-1480381 ; https://renewablesnow.com/news/h2-green-steel-signs-binding-offtake-deal-with-mercedes-benz-825303/ ; https://www.txfnews.com/articles/7631/h2-green-steel-boden-long-on-ambitions-low-on-emissions
- Stegra pre-sales (May 2022): https://www.globalhydrogenreview.com/hydrogen/20052022/h2-green-steel-has-pre-sold-over-15-million-t-of-green-steel-to-customers/
- Atome offtake with Yara (Sep 2025): https://www.ajbell.co.uk/news/articles/atome-signs-offtake-deal-yara-sell-entire-output-villeta
- IDB Invest approval (19 Nov 2025): https://www.worldfertilizer.com/environment/19112025/idb-invest-approves-us200-million-for-atomes-villeta-project/
- Atome definitive debt (13 Mar 2026): https://www.investegate.co.uk/announcement/rns/atome-energy--atom/atome-signs-definitive-debt-agreements-/9472496
- Atome equity and FID (23 Apr 2026): https://www.investegate.co.uk/announcement/rns/atome-energy--atom/equity-agreements-and-fid-for-villeta-project-/9535764
- Maersk–Goldwind (22 Nov 2023): https://www.maersk.com/news/articles/2023/11/22/maersk-signs-landmark-green-methanol-offtake-agreement
- Egypt Green Hydrogen offtake (Jul 2024): https://www.scatec.com/en/scatecs-egypt-green-hydrogen-project-signed-20-year-offtake-agreement-with-fertiglobe-based-on-h2global-award/ ; status Jan 2026: https://www.pv-magazine.com/2026/01/16/the-hydrogen-stream-scatec-led-100-mw-green-project-in-egypt-begins-operations/
- Infinium FID (19 May 2025): https://www.prnewswire.com/news-releases/infinium-announces-construction-of-large-scale-efuels-production-facility-in-texas-302458185.html ; IAG offtake: https://www.greenairnews.com/?p=6271
- Twelve AirPlant One opening (10 Jun 2026): https://www.twelve.co/post/airplant-one-opens-in-moses-lake-america-s-first-commercial-e-jet-fuel-plant-begins-operations
- SkyNRG financial close (12 Feb 2026): https://skynrg.com/dsl-01-delfzijl-financial-close/ ; https://www.greenairnews.com/?p=8526
- Uniper–Arcadia (23 Sep 2026): https://www.uniper.energy/news/uniper-and-arcadia-efuels-sign-long-term-agreement-to-accelerate-aviation-decarbonization
- FlagshipONE cancellation (Aug 2024): https://bioenergyinternational.com/orsted-halts-development-of-flagshipone/ ; https://industrydecarbonization.com/news/why-no-one-wanted-to-buy-the-green-shipping-fuel.html
- OIES ET52, Bankability of Hydrogen Projects (Jan 2026): https://www.oxfordenergy.org/wpcms/wp-content/uploads/2026/01/ET52-Bankability-of-Hydrogen-Projects.pdf
- GH2, Financing Green Hydrogen Projects (Dec 2022): https://gh2.org/sites/default/files/2022-12/GH2_Contracting%20Guidance_Financing%20Green%20Hydrogen%20Projects_2022.pdf
- IF25 draft Terms and Conditions: https://climate.ec.europa.eu/document/download/ee3b468a-ee39-4748-b3be-5ce8f0fd4652_en?filename=policies_if_draft_tc_if25_auction_h2_en.pdf
- IF25 CINEA Q&A v0.2 (3 Feb 2026): https://cinea.ec.europa.eu/document/download/923767e1-73a3-47c8-8ed6-510b80a1e7a3_en?A_IF25Hydrogen.pdf=&filename=Q
- IF25 auction page: https://climate.ec.europa.eu/areas-action/eu-funding-climate-action/innovation-fund/calls-proposals/if25-hydrogen-auction_en ; IEA summary: https://www.iea.org/policies/28480-third-auction-of-european-hydrogen-bank-ehb ; T. Harper (7 May 2026): https://timharper.net/european-hydrogen-auction-explained-if25/
- UK SAF RCM allocation strategy (Jul 2026): https://www.gov.uk/government/publications/sustainable-aviation-fuel-saf-revenue-certainty-mechanism-contract-allocation-strategy ; HSF Kramer note: https://www.hsfkramer.com/notes/energy/2026-posts/sustainable-aviation-fuel-uk-revenue-certainty-mechanism
- Plug Power DOE closing (16 Jan 2025): https://www.ir.plugpower.com/press-releases/news-details/2025/Plug-Closes-Loan-Guarantee-from-the-U.S.-Department-of-Energy/default.aspx ; suspension (Q3 2025 10-Q): https://www.sec.gov/Archives/edgar/data/1093691/000110465925109279/plug-20250930x10q.htm
- Montana Renewables DOE: https://www.energy.gov/edf/montana-renewables ; https://www.safinvestor.com/news/146723/montana-renewables-4/
- Gevo withdrawal (15 Apr 2026): https://finance.yahoo.com/sectors/energy/articles/gevo-withdraws-department-energy-financing-211500357.html ; extension: https://www.stocktitan.net/sec-filings/GEVO/8-k-gevo-inc-reports-material-event-bcd2ae6671d5.html
- APMG PPP Guide, Financial close: https://ppp-certification.com/ppp-certification-guide/13-financial-close
- Designing Buildings, Financial close: https://www.designingbuildings.co.uk/wiki/Financial_close
- Latham & Watkins, Book of Jargon — Project Finance: https://www.lw.com/admin/Upload/Documents/BoJ_Project_FInance_Third_Edition.pdf
- Marsh hydrogen insurance facility (2022): https://www.marsh.com/en/about/media/worlds-first-insurance-facility-for-green-and-blue-hydrogen-project.html
