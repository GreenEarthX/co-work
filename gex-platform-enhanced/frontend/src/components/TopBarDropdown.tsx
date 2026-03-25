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
      <div className="absolute top-full left-0 mt-1 w-72 bg-gray-900 border border-gray-700 rounded-lg shadow-2xl py-3 px-4 z-50">
        <p className="text-xs text-gray-500 italic">
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
      className="absolute top-full left-0 mt-1 w-72 bg-gray-900 border border-gray-700 rounded-lg shadow-2xl py-2 z-50"
      style={{ maxHeight: '60vh', overflowY: 'auto' }}
    >
      {sections.map((section, si) => (
        <div key={si}>
          {section.header && (
            <>
              {si > 0 && <div className="border-t border-gray-800 my-1.5" />}
              <div className="px-4 py-1.5">
                <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-gray-500">
                  {section.header}
                </span>
              </div>
            </>
          )}
          {!section.header && si > 0 && sections[si - 1].header && (
            <div className="border-t border-gray-800 my-1.5" />
          )}
          {section.items.map((item) => (
            <button
              key={item.id}
              onClick={() => { navigate(item.path); onClose(); }}
              className={`flex items-center justify-between px-4 py-2 text-sm w-full text-left
                transition-colors cursor-pointer
                ${location.pathname === item.path
                  ? 'text-teal-400 bg-teal-900/20'
                  : 'text-gray-300 hover:text-white hover:bg-gray-800'
                }`}
            >
              <span>{item.label}</span>
              {item.is_new && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-teal-900/50 text-teal-400">
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
