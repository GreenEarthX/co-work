// Screen: Shared component (no screen)
/**
 * One line: the phase the project declares against the state its evidence
 * supports. Both halves come from one engine readout. The phase is the one the
 * engine was told (project context), so the two can be read against each other.
 */
import { useVocabularyLabel } from "@/hooks/useEngineReadout";
import type { EngineReadout } from "@/lib/engineReadout";

type Props = {
  readout: Pick<
    EngineReadout,
    "project_phase" | "current_state" | "state_label" | "total_verified" | "total_evidence"
  >;
  className?: string;
};

export function DeclaredVsEvidenced({ readout, className = "" }: Props) {
  const phaseLabel = useVocabularyLabel("project_phase");
  const stateLabel = useVocabularyLabel("readiness");
  const phase = phaseLabel(readout.project_phase);

  return (
    <p
      data-testid="declared-vs-evidenced"
      className={`flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs text-[var(--text-secondary)] ${className}`}
    >
      <span>
        Declared phase{" "}
        <strong className="font-semibold text-[var(--text-primary)]">{phase ?? "not recorded"}</strong>
      </span>
      <span aria-hidden="true">·</span>
      <span>
        Evidenced state{" "}
        <strong className="font-semibold text-[var(--text-primary)]">
          {stateLabel(readout.current_state)}
        </strong>
      </span>
      {readout.state_label && (
        <>
          <span aria-hidden="true">·</span>
          <span>{readout.state_label}</span>
        </>
      )}
      <span aria-hidden="true">·</span>
      <span>
        {readout.total_verified} of {readout.total_evidence} applicable evidence items verified
      </span>
    </p>
  );
}
