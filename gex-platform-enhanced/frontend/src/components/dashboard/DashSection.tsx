// Screen: Shared component — Main dashboard screen
//
// A dashboard is an overview, not a document. Each block collapses behind a
// chevron so the whole picture fits one screen, and the header keeps carrying
// its summary while collapsed — a closed section still tells you something,
// otherwise collapsing is just hiding.
import { type ReactNode, useCallback, useEffect, useState } from "react";

const STORAGE_PREFIX = "gex_dash_section:";

/** Persisted per section so the user's chosen overview survives a reload. */
function useSectionOpen(id: string, defaultOpen: boolean) {
  const [open, setOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem(`${STORAGE_PREFIX}${id}`);
    return saved === null ? defaultOpen : saved === "1";
  });

  useEffect(() => {
    localStorage.setItem(`${STORAGE_PREFIX}${id}`, open ? "1" : "0");
  }, [id, open]);

  return [open, useCallback(() => setOpen((o) => !o), [])] as const;
}

export function DashSection({
  id,
  title,
  meta,
  defaultOpen = false,
  children,
}: {
  /** Stable key for the persisted open/closed state. */
  id: string;
  title: string;
  /** Summary shown on the header row — visible open OR closed, so a collapsed
   *  section still reports its headline number. */
  meta?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, toggle] = useSectionOpen(id, defaultOpen);

  return (
    <section className="rounded-xl border border-gray-200 bg-white">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-gray-50"
      >
        <svg
          viewBox="0 0 10 10"
          className="h-[10px] w-[10px] shrink-0 text-gray-400 transition-transform duration-150"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
          aria-hidden="true"
        >
          <path
            d="M3 2 L7 5 L3 8"
            stroke="currentColor"
            strokeWidth="1.6"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-900">
          {title}
        </span>
        {meta && (
          <span className="ml-auto flex min-w-0 items-center gap-2 truncate text-[11px] text-gray-500">
            {meta}
          </span>
        )}
      </button>
      {open && <div className="border-t border-gray-100 p-4">{children}</div>}
    </section>
  );
}

/** Compact count/label pill for a section header's `meta` slot. */
export function SectionMeta({
  value,
  label,
  tone = "neutral",
}: {
  value: ReactNode;
  label: string;
  tone?: "neutral" | "warn" | "bad";
}) {
  const cls =
    tone === "bad"
      ? "text-red-700"
      : tone === "warn"
        ? "text-amber-700"
        : "text-gray-900";
  return (
    <span className="flex items-center gap-1 whitespace-nowrap">
      <span className={`font-bold tabular-nums ${cls}`}>{value}</span>
      <span className="uppercase tracking-[0.1em] text-gray-400">{label}</span>
    </span>
  );
}
