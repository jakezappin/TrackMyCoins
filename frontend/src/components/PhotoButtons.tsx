import { useRef } from "react";

/**
 * "Take photo" (opens the camera on phones) and "Choose photos" buttons.
 * On a computer both open the file picker.
 */
export default function PhotoButtons({
  onFiles,
  multiple = true,
  takeLabel = "Take photo",
  chooseLabel = "Choose photos",
  disabled,
  primary,
}: {
  onFiles: (files: File[]) => void;
  multiple?: boolean;
  takeLabel?: string;
  chooseLabel?: string;
  disabled?: boolean;
  primary?: boolean;
}) {
  const camera = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const handle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // allow choosing the same file again
    if (files.length) onFiles(files);
  };
  return (
    <span className="photo-buttons">
      <button type="button" className={`btn${primary ? " btn-primary" : ""}`} disabled={disabled} onClick={() => camera.current?.click()}>
        <span className="btn-icon" aria-hidden="true">📷</span>
        {takeLabel}
      </button>
      <button type="button" className="btn" disabled={disabled} onClick={() => picker.current?.click()}>
        {chooseLabel}
      </button>
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={handle} />
      <input ref={picker} type="file" accept="image/*" multiple={multiple} hidden onChange={handle} />
    </span>
  );
}
