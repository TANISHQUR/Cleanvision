import { useEffect, useState } from "react";
import { api } from "../api.js";

// Search the simulated registry and pick the person seen in the clip.
export default function CitizenPicker({ value, onChange }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api.citizens(q).then((r) => setResults(r.items.slice(0, 8))).catch(setError);
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  if (value) {
    return (
      <div className="picked">
        <div>
          <strong>{value.name}</strong>
          <div className="muted num">{value.citizen_ref}, {value.address}</div>
        </div>
        <button type="button" className="link-button" onClick={() => onChange(null)}>Change</button>
      </div>
    );
  }

  return (
    <div className="picker">
      <label className="field">
        <span>Person in the clip</span>
        <input type="search" placeholder="Search by name, ID or area" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {error && <p className="error-note">{error.message}</p>}
      <ul className="picker-list" role="listbox">
        {results.map((c) => (
          <li key={c.id}>
            <button type="button" onClick={() => onChange(c)}>
              <span>{c.name}</span>
              <span className="muted num">
                {c.citizen_ref}
                {c.violation_count > 0 && `, ${c.violation_count} earlier`}
              </span>
            </button>
          </li>
        ))}
        {results.length === 0 && <li className="muted">No one matches “{q}”.</li>}
      </ul>
      <p className="hint">The registry is simulated for this prototype. All records are fictional.</p>
    </div>
  );
}
