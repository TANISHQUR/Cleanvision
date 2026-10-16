import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { ErrorNote, Loading, PageHeader } from "../components/ui.jsx";

export default function Citizens() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => api.citizens(q).then((r) => setItems(r.items)).catch(setError), 200);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <>
      <PageHeader title="Citizen registry"
        lead="A simulated identity database for the demo. Every record here is fictional.">
        <input className="search" type="search" placeholder="Search name, ID or area" value={q}
          onChange={(e) => setQ(e.target.value)} aria-label="Search citizens" />
      </PageHeader>
      <ErrorNote error={error} />
      {!items ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Registry ID</th>
                <th>Address</th>
                <th>Phone</th>
                <th className="right">Incidents</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="row-link" tabIndex={0} onClick={() => navigate(`/citizens/${c.id}`)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(`/citizens/${c.id}`)}>
                  <td><strong>{c.name}</strong></td>
                  <td className="num">{c.citizen_ref}</td>
                  <td>{c.address}</td>
                  <td className="num">{c.phone}</td>
                  <td className="num right">{c.violation_count || ""}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={5} className="muted">No one matches “{q}”.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
