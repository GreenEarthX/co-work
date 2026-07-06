import { ChevronDown, ChevronRight, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

interface SectionPanelProps {
  id: string;
  label: string;
  icon: LucideIcon;
  count: number;
  filled: number;
  open: boolean;
  onToggle: (id: string) => void;
  children: React.ReactNode;
}

const SectionPanel = ({
  id,
  label,
  icon: Icon,
  count,
  filled,
  open,
  onToggle,
  children,
}: SectionPanelProps) => {
  return (
    <section className="rounded-xl border border-border bg-card/80 backdrop-blur-sm overflow-hidden">
      <button
        type="button"
        onClick={() => onToggle(id)}
        className="w-full px-4 py-3 flex items-center gap-2.5 text-left hover:bg-accent/40 transition-colors"
      >
        <span className="h-7 w-7 rounded-md bg-muted flex items-center justify-center shrink-0">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        </span>
        <span className="flex-1 text-sm font-semibold text-foreground">{label}</span>
        <Badge variant="secondary" className="text-[10px] font-mono">
          {filled}/{count}
        </Badge>
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>

      {open && <div className="px-4 pb-4 pt-1">{children}</div>}
    </section>
  );
};

export default SectionPanel;
