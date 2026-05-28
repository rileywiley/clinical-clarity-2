/**
 * Block exit when a form has unsaved changes.
 *
 * Per project memory (feedback-unsaved-changes-guard): every Save-button form
 * must prompt the user before they navigate away with dirty state. Three
 * routes a user can leave through, all handled here:
 *
 *   1. React Router navigation (Link, programmatic push) — useBlocker
 *   2. Tab/window close, refresh — beforeunload
 *   3. (Hash navigation, in-app redirects via setLocation, etc.) — useBlocker
 *
 * Returns a small API the caller can wire to a custom dialog if it wants to
 * replace the browser-native confirm. Phase 3 ships with the native confirm
 * to keep the surface small; a styled dialog can come in Phase 6 polish.
 */

import { useEffect } from "react";
import { useBlocker } from "react-router-dom";

export type UseUnsavedChangesGuardOptions = {
  /** When true, the guard is active. When false, navigation/close are unblocked. */
  dirty: boolean;
  /** Message shown in the native confirm. Browser may override for beforeunload. */
  message?: string;
};

export function useUnsavedChangesGuard({
  dirty,
  message = "You have unsaved changes. Leave anyway?",
}: UseUnsavedChangesGuardOptions) {
  // 1. React Router navigation guard.
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (!dirty) return false;
    // Don't block reloads to the same URL (e.g. on Save success the page may
    // refetch and trigger a same-path nav).
    if (currentLocation.pathname === nextLocation.pathname) return false;
    return true;
  });

  useEffect(() => {
    if (blocker.state === "blocked") {
      const proceed = window.confirm(message);
      if (proceed) blocker.proceed();
      else blocker.reset();
    }
  }, [blocker, message]);

  // 2. Tab close / refresh / external nav.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      // Modern browsers ignore the message and show their own — but setting
      // returnValue + calling preventDefault is what triggers the prompt.
      e.preventDefault();
      e.returnValue = message;
      return message;
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty, message]);
}
