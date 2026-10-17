import { useState } from "react";

/** Open/closed state for a card, remembered on this device. */
export default function useCollapsed(key: string): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(key) === "1";
    } catch {
      return false;
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
