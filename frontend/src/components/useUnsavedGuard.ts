import { useEffect, useRef, type MutableRefObject } from "react";
import { useBlocker } from "react-router-dom";

/** Asks before leaving a form with unsaved changes: Back, a link, Cancel, or closing or reloading the tab. Set the
 * returned ref's `current` to true just before leaving on purpose (after saving), so that doesn't ask. */
export function useUnsavedGuard(dirty: boolean, message: string, leaving?: MutableRefObject<boolean>): MutableRefObject<boolean> {
  const own = useRef(false);
  const ref = leaving ?? own;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && !ref.current && currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(message)) blocker.proceed();
    else blocker.reset();
  }, [blocker, message]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      if (ref.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, ref]);
  return ref;
}
