import { useEffect, useRef, type ReactNode } from "react";

/** "More ▾" button with a drop-down of less-used actions. Closes on an outside click, Escape, or after a choice. */
export default function MoreMenu({ children, label = "More" }: { children: ReactNode; label?: string }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (e: Event) => {
      const el = ref.current;
      if (!el?.open) return;
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !el.contains(e.target as Node)) el.open = false;
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", close);
    };
  }, []);
  return (
    <details className="menu more-menu" ref={ref}>
      <summary className="btn">
        {label} <span aria-hidden="true">▾</span>
      </summary>
      <div
        className="menu-pop"
        onClick={(e) => {
          if ((e.target as HTMLElement).closest("a, button") && ref.current) ref.current.open = false;
        }}
      >
        {children}
      </div>
    </details>
  );
}
