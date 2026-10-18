import { useState } from "react";
import { downloadFile } from "../api";

/** A link that downloads a report or export, and shows a failure as a message instead of saving it as the file. */
export default function DownloadLink({ href, className, children }: { href: string; className?: string; children: React.ReactNode }) {
  const [busy, setBusy] = useState(false);
  return (
    <a
      href={href}
      className={className}
      aria-busy={busy}
      onClick={async (e) => {
        e.preventDefault();
        if (busy) return;
        setBusy(true);
        try {
          await downloadFile(href);
        } catch (err) {
          window.alert(`Couldn't download: ${(err as Error).message}`);
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Preparing…" : children}
    </a>
  );
}
