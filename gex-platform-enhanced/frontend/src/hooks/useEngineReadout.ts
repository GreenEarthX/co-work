// Screen: Hook (no screen)
/**
 * One cached engine readout per project, shared by /projects, State & Blockers
 * and Capital Eligibility, so the three screens cannot disagree. No fixture
 * fallback: when the engine does not answer, callers get the error and say so.
 */
import { useCallback } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { bankabilityAPI, vocabularyAPI } from "@/api";
import { humanise, type EngineReadout } from "@/lib/engineReadout";

const READOUT_STALE_MS = 60_000;

function readoutQuery(projectId: string | undefined) {
  return {
    queryKey: ["engine-readout", projectId],
    queryFn: () => bankabilityAPI.readout(projectId!) as Promise<EngineReadout>,
    enabled: !!projectId,
    staleTime: READOUT_STALE_MS,
  };
}

export function useEngineReadout(projectId: string | undefined) {
  return useQuery(readoutQuery(projectId));
}

export function useEngineReadouts(projectIds: string[]) {
  return useQueries({ queries: projectIds.map((id) => readoutQuery(id)) });
}

/** Engine rules: persona gates, capital semantics, level definitions. */
export interface EngineRules {
  rules_version?: string;
  capital_semantics?: string;
  persona_gates?: Record<string, string[]>;
}

export function useEngineRules() {
  return useQuery({
    queryKey: ["engine-rules"],
    queryFn: () => bankabilityAPI.getRules() as Promise<EngineRules>,
    staleTime: Infinity,
  });
}

interface VocabularyConcept {
  terms: Array<{ canonical: string; label: string }>;
}

/**
 * Label lookup for one vocabulary concept ("readiness" = the engine's states,
 * "project_phase" = the declared phase). Returns null for a missing value.
 */
export function useVocabularyLabel(concept: "readiness" | "project_phase") {
  const { data } = useQuery({
    queryKey: ["vocabulary", concept],
    queryFn: () => vocabularyAPI.concept(concept) as Promise<VocabularyConcept>,
    staleTime: Infinity,
  });
  return useCallback(
    (canonical: string | null | undefined): string | null => {
      if (!canonical) return null;
      return data?.terms.find((t) => t.canonical === canonical)?.label ?? humanise(canonical);
    },
    [data],
  );
}
