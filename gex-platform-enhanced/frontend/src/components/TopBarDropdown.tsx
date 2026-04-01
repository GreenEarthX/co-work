import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

interface DropdownItem {
  id: string;
  path: string;
  label: string;
  section: string;
  is_new?: boolean;
}

export function TopBarDropdown({
  label,
  items,
  isActive,
  onClose,
}: {
  label: string;
  items: DropdownItem[];
  isActive: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();

  if (items.length === 0) {
    return (
      <div
        className="absolute top-full left-0 mt-2 w-72 rounded-xl py-3 px-4 z-50"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          boxShadow: '0 18px 40px rgba(22, 33, 29, 0.08)',
        }}
      >
        <p className="text-xs italic" style={{ color: 'var(--text-muted)' }}>
          No items for your role on this project.
        </p>
      </div>
    );
  }

  // Group items by section
  const sections: { header: string; items: DropdownItem[] }[] = [];
  let currentSection = '';
  let currentGroup: DropdownItem[] = [];

  for (const item of items) {
    if (item.section !== currentSection) {
      if (currentGroup.length > 0) {
        sections.push({ header: currentSection, items: currentGroup });
      }
      currentSection = item.section;
      currentGroup = [item];
    } else {
      currentGroup.push(item);
    }
  }
  if (currentGroup.length > 0) {
    sections.push({ header: currentSection, items: currentGroup });
  }

  return (
    <div
      className="absolute top-full left-0 mt-2 w-72 rounded-xl py-2 z-50"
      style={{
        maxHeight: '60vh',
        overflowY: 'auto',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        boxShadow: '0 18px 40px rgba(22, 33, 29, 0.08)',
      }}
    >
      {sections.map((section, si) => (
        <div key={si}>
          {section.header && (
            <>
              {si > 0 && <div className="my-1.5" style={{ borderTop: '1px solid var(--border)' }} />}
              <div className="px-4 py-1.5">
                <span className="text-[10px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--text-muted)' }}>
                  {section.header}
                </span>
              </div>
            </>
          )}
          {!section.header && si > 0 && sections[si - 1].header && (
            <div className="my-1.5" style={{ borderTop: '1px solid var(--border)' }} />
          )}
          {section.items.map((item) => (
            <button
              key={item.id}
              onClick={() => { navigate(item.path); onClose(); }}
              className="flex items-center justify-between px-4 py-2.5 text-sm w-full text-left transition-colors cursor-pointer rounded-lg"
              style={location.pathname === item.path
                ? { color: 'var(--text-primary)', background: 'var(--surface-muted)' }
                : { color: 'var(--text-secondary)' }}
            >
              <span>{item.label}</span>
              {item.is_new && (
                <span
                  className="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                  style={{ background: 'var(--brand-light)', color: 'var(--brand)' }}
                >
                  NEW
                </span>
              )}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
