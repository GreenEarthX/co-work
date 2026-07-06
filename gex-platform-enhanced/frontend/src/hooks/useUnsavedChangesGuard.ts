/**
 * useUnsavedChangesGuard — Blocks navigation away from a page when there
 * are unsaved changes.  Works with <BrowserRouter> (no data-router needed).
 *
 * Strategy:
 *  1. Monkey-patches history.pushState / replaceState so clicks on <Link>
 *     or navigate() are intercepted before the route changes.
 *  2. Listens to popstate for browser back/forward.
 *  3. Listens to beforeunload for tab close / refresh.
 *
 * IMPORTANT: proceed() only clears internal blocking state — callers are
 * responsible for performing the actual SPA navigation via react-router's
 * navigate(). This avoids hard browser navigations that lose preview context.
 */
import { useEffect, useCallback, useRef } from "react";
import { ensurePreviewParams } from "@/lib/preservePreviewParams";

interface Options {
  isDirty: boolean;
  onBlock: (pendingUrl: string) => void;
}

export function useUnsavedChangesGuard({ isDirty, onBlock }: Options) {
  const pendingUrl = useRef<string | null>(null);
  const isDirtyRef = useRef(isDirty);
  isDirtyRef.current = isDirty;

  // Store the current pathname so popstate can restore it accurately
  const currentPathRef = useRef(window.location.pathname + window.location.search);
  useEffect(() => {
    currentPathRef.current = window.location.pathname + window.location.search;
  });

  // ---------- history.pushState / replaceState interception ----------
  useEffect(() => {
    if (!isDirty) return;

    const origPush = history.pushState.bind(history);
    const origReplace = history.replaceState.bind(history);

    const intercept =
      (original: typeof history.pushState): typeof history.pushState =>
      function (this: History, data, unused, url) {
        if (isDirtyRef.current && url) {
          const targetPath = String(url);
          // Allow same-page writes (e.g. search-param updates, preview param restoration)
          const currentBase = location.pathname;
          const targetBase = targetPath.split("?")[0].split("#")[0];
          if (targetBase !== currentBase) {
            pendingUrl.current = targetPath;
            onBlock(targetPath);
            return; // swallow, the dialog will call proceed() or reset()
          }
        }
        const result = original.call(this, data, unused, url);
        ensurePreviewParams();
        return result;
      };

    history.pushState = intercept(origPush);
    history.replaceState = intercept(origReplace);

    return () => {
      history.pushState = origPush;
      history.replaceState = origReplace;
    };
  }, [isDirty, onBlock]);

  // ---------- popstate (browser back/forward) ----------
  useEffect(() => {
    if (!isDirty) return;
    const handler = () => {
      // The browser has already changed the URL. Capture where it tried to go.
      const attemptedUrl = location.pathname + location.search;
      // Push current page back so the user stays here visually.
      // Use the original pushState if it hasn't been restored yet.
      window.history.pushState(null, "", currentPathRef.current);
      pendingUrl.current = attemptedUrl;
      onBlock(attemptedUrl);
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, [isDirty, onBlock]);

  // ---------- beforeunload (tab close / refresh) ----------
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  /**
   * Clear internal blocking state so subsequent navigations are not blocked.
   * Callers MUST perform the actual SPA navigation themselves (e.g. navigate(url)).
   * This intentionally does NOT do window.location.assign to avoid losing
   * preview context / query tokens.
   */
  const proceed = useCallback(() => {
    pendingUrl.current = null;
    isDirtyRef.current = false;
  }, []);

  /** Cancel the pending navigation — stay on page */
  const reset = useCallback(() => {
    pendingUrl.current = null;
  }, []);

  return { proceed, reset };
}
