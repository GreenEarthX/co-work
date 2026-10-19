"""Independent replica of the Hydrogen FM, plus stress cases. Not read from the workbook's formulas."""
def irr(cfs, lo=-0.99, hi=1.0):
    f=lambda r: sum(c/(1+r)**t for t,c in enumerate(cfs))
    for _ in range(200):
        m=(lo+hi)/2
        if f(lo)*f(m)<=0: hi=m
        else: lo=m
    return m
def npv(r,cfs): return sum(c/(1+r)**t for t,c in enumerate(cfs))

def run(prod=1.7e6, price=3.0, capex=15e6, fees=155e3, debt=7.5e6, life=30, om=225e3, water=35.7e3,
        elec=3.0e6, ins=75e3, tax=0.21, dep=10, rate=0.04, tenor=10, ke=0.05, kp=0.05,
        degr=0.0, stack_cost=0.0, stack_every=0, infl=0.0, price_esc=0.0):
    eq=capex+fees-debt
    e_cf=[-eq]; p_cf=[-capex]; cfads=[]; ds=[]; bal=debt; losses=0; losses_u=0
    for t in range(1,life+1):
        q=prod*(1-degr)**(t-1)                       # degradation cuts output at fixed power
        rev=q*price*(1+price_esc)**(t-1)
        opex=(om+water+ins)*(1+infl)**(t-1)+elec*(1+infl)**(t-1)
        rep=stack_cost if (stack_every and t%stack_every==0 and t<life) else 0
        ebitda=rev-opex
        d=capex/dep if t<=dep else 0
        i=bal*rate if t<=tenor else 0
        p=debt/tenor if t<=tenor else 0
        ti=ebitda-i-d; use=min(losses,max(0,ti)); losses+=max(0,-ti)-use; tx=max(0,ti-use)*tax
        tu=ebitda-d; useu=min(losses_u,max(0,tu)); losses_u+=max(0,-tu)-useu; txu=max(0,tu-useu)*tax
        cf=ebitda-tx-rep
        cfads.append(cf); ds.append(i+p)
        e_cf.append(cf-i-p); p_cf.append(ebitda-txu-rep); bal-=p
    dscr=[c/s for c,s in zip(cfads,ds) if s>0]
    llcr=npv(rate,[0]+cfads[:tenor])/debt if debt else None
    return dict(eq_irr=irr(e_cf), eq_npv=npv(ke,e_cf), pr_irr=irr(p_cf), pr_npv=npv(kp,p_cf),
                min_dscr=min(dscr) if dscr else None, llcr0=llcr)

base=run()
print('BASE replica', {k:round(v,4) for k,v in base.items()})
kwh=55; mwh=1.7e6*kwh/1000
print(f'implied power: {mwh:,.0f} MWh/yr at {kwh} kWh/kg -> USD {3e6/mwh:.1f}/MWh; '
      f'electricity = USD {3e6/1.7e6:.2f}/kg of the 3.00 price')
for cf in (0.95,0.57):
    mw=mwh/8760/cf; print(f'  at capacity factor {cf:.0%}: {mw:.1f} MW -> capex USD {15e6/mw/1e3:,.0f}/kW')

print('\nSTRESS (one change at a time, then combined)')
mw = 93_500/8760/0.74          # hybrid wind-PV capacity factor 74% (DOE record 24005)
capex_doe = 2_000*mw*1000       # USD 2,000/kW installed (DOE 24005; IEA: 2,000-2,600 outside China)
stack = 0.11*capex_doe          # 11% of installed capex every 40,000 h (DOE 24005)
every = round(40_000/(8760*0.74))
cases = {
 'base (PDF)':                     {},
 'capex USD 2,000/kW':             dict(capex=capex_doe, debt=capex_doe/2),
 'stack replacement':              dict(stack_cost=stack, stack_every=every),
 'degradation 1%/yr output':       dict(degr=0.01),
 'debt at 6%':                     dict(rate=0.06),
 'combined (all four)':            dict(capex=capex_doe, debt=capex_doe/2, stack_cost=stack, stack_every=every, degr=0.01, rate=0.06),
}
for k,kw in cases.items():
    r=run(**kw); print(f"  {k:28} equity IRR {r['eq_irr']:7.2%}  project IRR {r['pr_irr']:7.2%}  min DSCR {r['min_dscr']:.2f}  LLCR {r['llcr0']:.2f}")
print(f'  (hybrid case: {mw:.1f} MW, capex USD {capex_doe/1e6:.1f}m, stack USD {stack/1e6:.2f}m every {every} yrs)')

def price_for(target, key='eq_irr', **kw):
    lo,hi=0.5,20
    for _ in range(60):
        m=(lo+hi)/2
        if run(price=m,**kw)[key]<target: lo=m
        else: hi=m
    return m
comb=cases['combined (all four)']
print(f"  price for 10% equity IRR, combined case: USD {price_for(0.10, **comb):.2f}/kg")
print(f"  price for min DSCR 1.30, combined case: USD {price_for(1.30, key='min_dscr', **comb):.2f}/kg")
