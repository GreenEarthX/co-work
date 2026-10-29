// Screen: Shared layout component — all authenticated screens
import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

interface DropdownItem {
  id: string;
  path: string;
  label: string;
  section: string;
}

export function TopBarDropdown({
  label: _label,
  items,
  isActive: _isActive,
  onClose,
}: {
  label: string;
  items: DropdownItem[];
  isActive: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();

  // Group items by section, preserving order. Blank-header items form the
  // always-visible "core" group; named sections become collapsible accordions.
  const sections = useMemo(() => {
    const out: { header: string; items: DropdownItem[] }[] = [];
    let cur = '';
    let group: DropdownItem[] = [];
    for (const item of items) {
      if (item.section !== cur) {
        if (group.length) out.push({ header: cur, items: group });
        cur = item.section;
        group = [item];
      } else {
        group.push(item);
      }
    }
    if (group.length) out.push({ header: cur, items: group });
    return out;
  }, [items]);

  // Accordion open-state for NAMED sections. Default: open the section that
  // contains the active route; collapse the rest so a long dropdown (Finance)
  // opens as a short scan, not a 20-row wall.
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const s of sections) {
      if (!s.header) continue;
      init[s.header] = s.items.some(i => i.path === location.pathname);
    }
    return init;
  });
  const toggle = (header: string) =>
    setOpenSections(prev => ({ ...prev, [header]: !prev[header] }));

  if (items.length === 0) {
    return (
      <div
        className="absolute top-full left-0 mt-2 w-72 rounded-xl py-3 px-4 z-50"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: '0 18px 40px rgba(22, 33, 29, 0.08)' }}
      >
        <p className="text-xs italic" style={{ color: 'var(--text-muted)' }}>
          No items for your role on this project.
        </p>
      </div>
    );
  }

  const renderItem = (item: DropdownItem) => {
    // No screen locks or gate badges in the menu (JML 2026-10-28): what a user
    // may do is decided by the server, and a client-side lock read hand-typed
    // gate figures and blocked the very work that completes a gate.
    return (
      <button
        key={item.id}
        onClick={() => { navigate(item.path); onClose(); }}
        className="flex items-center justify-between gap-2 px-4 py-2 text-sm w-full text-left transition-colors cursor-pointer rounded-lg"
        style={location.pathname === item.path
          ? { color: 'var(--text-primary)', background: 'var(--surface-muted)' }
          : { color: 'var(--text-secondary)' }}
      >
        <span className="flex items-center gap-1.5 min-w-0">
          <span className="truncate">{item.label}</span>
        </span>
      </button>
    );
  };

  return (
    <div
      className="absolute top-full left-0 mt-2 w-72 rounded-xl py-2 z-50"
      style={{ maxHeight: '70vh', overflowY: 'auto', background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: '0 18px 40px rgba(22, 33, 29, 0.08)' }}
    >
      {sections.map((section, si) => {
        // Blank-header section → always-visible core group.
        if (!section.header) {
          return <div key={si}>{section.items.map(renderItem)}</div>;
        }
        // Named section → collapsible accordion header + body.
        const open = openSections[section.header];
        const panelId = `menu-acc-${section.header.replace(/\s+/g, '-').toLowerCase()}`;
        return (
          <div key={si}>
            {si > 0 && <div className="my-1" style={{ borderTop: '1px solid var(--border)' }} />}
            <button
              type="button"
              onClick={() => toggle(section.header)}
              aria-expanded={open}
              aria-controls={panelId}
              className="flex w-full items-center justify-between px-4 py-1.5 hover:bg-[var(--surface-muted)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand,#0ea5a0)] transition-colors"
            >
              <span className="flex items-center gap-1.5">
                {open
                  ? <ChevronDown className="w-3 h-3" aria-hidden="true" style={{ color: 'var(--text-muted)' }} />
                  : <ChevronRight className="w-3 h-3" aria-hidden="true" style={{ color: 'var(--text-muted)' }} />}
                <span className="text-[10px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--text-muted)' }}>
                  {section.header}
                </span>
              </span>
              {/* count always shown so collapsed sections stay discoverable */}
              <span className="text-[10px] font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
                {section.items.length}
              </span>
            </button>
            <div id={panelId} role="region" aria-label={section.header} hidden={!open}>
              {open && section.items.map(renderItem)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
