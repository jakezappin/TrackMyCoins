import { Link } from "react-router-dom";
import type { DuplicateCert } from "../api";
import { coinPath, collectionPath } from "../format";

interface Props {
  service: string;
  cert: string;
  duplicate: DuplicateCert;
  onClose: () => void;
}

export default function DuplicateCertModal({ service, cert, duplicate, onClose }: Props) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="alertdialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h2>Already in your collection</h2>
        <p>
          {service} cert <strong className="mono">{cert}</strong> is already{" "}
          <strong>{duplicate.inventory_number}</strong> ({duplicate.description}) in{" "}
          <Link
            to={collectionPath({ collection_type_slug: duplicate.collection_type_slug, number: duplicate.collection_number })}
            onClick={onClose}
          >
            {duplicate.collection_name}
          </Link>
          . A slab can only be in your collection once.
        </p>
        <p className="muted small">If you sold it and bought it back, mark the old entry as sold first.</p>
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
          <Link className="btn btn-primary" to={coinPath(duplicate.inventory_number)} onClick={onClose}>
            View {duplicate.inventory_number}
          </Link>
        </div>
      </div>
    </div>
  );
}
