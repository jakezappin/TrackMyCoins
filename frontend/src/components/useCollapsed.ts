import { useState } from "react";

/** Open/closed state for a card, remembered on this device. */
export default function useCollapsed(key: string, startCollapsed = false): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const v = localStorage.getItem(key);
      return v === null ? startCollapsed : v === "1";
    } catch {
      return startCollapsed;
    }
  });
  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem(key, c ? "0" : "1");
      } catch {
        // Remembering is only a convenience.
      }
      return !c;
    });
  return [collapsed, toggle];
}
