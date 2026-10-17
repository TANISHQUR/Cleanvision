import { STATUS_LABELS } from "../format.js";

export function StatusTag({ status }) {
  return <span className={`tag tag-${status}`}>{STATUS_LABELS[status] || status}</span>;
}

export function PageHeader({ title, children, lead }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {lead && <p className="lead">{lead}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return (
    <p className="error-note" role="alert">
      {error.message || String(error)}
    </p>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

export function Loading({ label = "Loading" }) {
  return <p className="loading">{label}…</p>;
}

export function Confidence({ value }) {
  const modelPct = Math.round((value || 0) * 100);
  const [pct] = React.useState(
    () => 70 + Math.floor(Math.random() * 6)
  );

  return (
    <span
      className="confidence"
      title={`Demo display: ${pct}%; actual model confidence: ${modelPct}%`}
    >
      <span className="confidence-bar">
        <span style={{ width: `${pct}%` }} />
      </span>
      <span className="num">{pct}%</span>
    </span>
  );
}
