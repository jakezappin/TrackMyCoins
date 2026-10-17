import { useEffect, useRef, useState } from "react";

/** A row of cards that scrolls sideways, about three at a time, with arrow buttons. */
export default function HScroll({ label, children }: { label: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  function update() {
    const el = ref.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 4);
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }

  useEffect(() => {
    update();
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [children]);

  function page(dir: 1 | -1) {
    const el = ref.current;
    if (el) el.scrollBy({ left: dir * el.clientWidth, behavior: "smooth" });
  }

  return (
    <div className="hscroll">
      <div className="hscroll-track" ref={ref} onScroll={update} role="region" aria-label={label} tabIndex={0}>
        {children}
      </div>
      {canLeft && (
        <button className="hscroll-btn left" onClick={() => page(-1)} aria-label={`Scroll ${label} left`}>
          ‹
        </button>
      )}
      {canRight && (
        <button className="hscroll-btn right" onClick={() => page(1)} aria-label={`Scroll ${label} right`}>
          ›
        </button>
      )}
    </div>
  );
}
