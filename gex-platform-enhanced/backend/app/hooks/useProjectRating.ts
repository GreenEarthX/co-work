import { useEffect, useState } from "react";
import { scoreProjectRating } from "@/lib/api/projectRatings";
import type { ProjectRatingRequest, ProjectRatingResponse } from "@/types/projectRating";

interface UseProjectRatingResult {
  data: ProjectRatingResponse | null;
  isLoading: boolean;
  error: string | null;
}

/**
 * Hook that computes a GEX Project Quality Rating from a payload.
 * Re-runs whenever `payload` changes (use useMemo on the caller side to stabilise).
 */
export function useProjectRating(
  payload: ProjectRatingRequest | null
): UseProjectRatingResult {
  const [data, setData] = useState<ProjectRatingResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!payload) return;

    let cancelled = false;

    async function run() {
      setIsLoading(true);
      setError(null);
      try {
        const result = await scoreProjectRating(payload!);
        if (!cancelled) setData(result);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        if (!cancelled) setError(message);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    run();
    return () => { cancelled = true; };
  }, [payload]);

  return { data, isLoading, error };
}
