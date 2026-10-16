import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, mediaUrl } from "../api.js";
import { ErrorNote, Loading, StatusTag } from "../components/ui.jsx";
import { formatDate, formatDateTime, formatMoney, wasteLabel } from "../format.js";

export default function CitizenDetail() {
  const { id } = useParams();
  const [c, setC] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.citizen(id).then(setC).catch(setError);
  }, [id]);

  if (error) return <ErrorNote error={error} />;
  if (!c) return <Loading />;

  const unpaid = c.challans.filter((x) => x.status === "issued").reduce((s, x) => s + x.amount, 0);

  return (
    <>
      <Link to="/citizens" className="back">Back to registry</Link>
      <header className="page-header">
        <div>
          <h1>{c.name}</h1>
          <p className="muted num">{c.citizen_ref}, {c.address}, {c.phone}</p>
        </div>
        <div className="figure figure-inline">
          <span className="figure-value num">{formatMoney(unpaid)}</span>
          <span className="figure-label">unpaid</span>
        </div>
      </header>

      <section className="panel">
        <h3>Incidents</h3>
        {c.violations.length === 0 ? (
          <p className="muted">No incidents linked to this person.</p>
        ) : (
          <ul className="recent">
            {c.violations.map((v) => (
              <li key={v.id}>
                <Link to={`/violations/${v.id}`}>
                  <img src={mediaUrl(`/api/media/${v.evidence.scene}`)} alt="" loading="lazy" />
                  <span className="recent-main">
                    <span><strong>{wasteLabel(v.waste_type)}</strong> at {v.location || v.camera_id}</span>
                    <span className="muted">{formatDateTime(v.detected_at)}</span>
                  </span>
                  <StatusTag status={v.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h3>Challans</h3>
        {c.challans.length === 0 ? (
          <p className="muted">None issued.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <tbody>
                {c.challans.map((x) => (
                  <tr key={x.id}>
                    <td className="num"><strong>{x.number}</strong></td>
                    <td>{formatDate(x.issued_at)}</td>
                    <td className="num right">{formatMoney(x.amount)}</td>
                    <td><span className={`pay pay-${x.status}`}>{x.status === "issued" ? "unpaid" : x.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
