import type { ReactNode } from "react";

/** Card heading that opens/closes the card, with optional controls on the right while open. */
export default function CollapseHead({
  title,
  collapsed,
  onToggle,
  children,
}: {
  title: string;
  collapsed: boolean;
  onToggle: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="section-head">
      <button type="button" className="collapse-toggle" onClick={onToggle} aria-expanded={!collapsed}>
        <span className="chev" aria-hidden="true">
          ▾
        </span>
        <h2>{title}</h2>
      </button>
      {!collapsed && children}
    </div>
  );
}
