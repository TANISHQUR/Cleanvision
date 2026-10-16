import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mediaUrl } from "../api.js";
import { ErrorNote, Loading, PageHeader, StatusTag } from "../components/ui.jsx";
import { formatMoney, timeAgo, wasteLabel } from "../format.js";

export default function Overview() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([api.stats(), api.violations({ limit: 6 })])
      .then(([s, v]) => {
        setStats(s);
        setRecent(v.items);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorNote error={error} />;
  if (!stats) return <Loading />;

  const maxDay = Math.max(1, ...stats.daily.map((d) => d.count));
  const types = Object.entries(stats.by_waste_type);
  const maxType = Math.max(1, ...types.map(([, n]) => n));
  const { pending, flagged, approved, rejected } = stats.by_status;

  return (
    <>
      <PageHeader title="Overview" />

      <section className="hero-queue">
        <div className="hero-sign" aria-hidden="true"><span>{pending}</span></div>
        <div className="hero-text">
          <h2>{pending === 1 ? "1 incident is waiting for review" : `${pending} incidents are waiting for review`}</h2>
          <p>
            {flagged > 0 ? `${flagged} more marked for a second look. ` : ""}
            Each one needs a person to check the clip before any challan goes out.
          </p>
        </div>
        {pending + flagged > 0 ? (
          <Link className="btn btn-primary" to={`/violations?status=${pending ? "pending" : "flagged"}`}>Start reviewing</Link>
        ) : (
          <Link className="btn" to="/upload">Analyse footage</Link>
        )}
      </section>

      <section className="figures">
        <Figure label="Challans issued" value={approved} />
        <Figure label="Dismissed" value={rejected} />
        <Figure label="Fines outstanding" value={formatMoney(stats.fines.issued_amount)} />
        <Figure label="Fines collected" value={formatMoney(stats.fines.paid_amount)} />
      </section>

      <div className="two-col">
        <section className="panel">
          <h3>Incidents in the last {stats.daily.length} days</h3>
          <div className="day-chart" role="img" aria-label="Incidents per day">
            {stats.daily.map((d) => (
              <div key={d.date} className="day" title={`${d.date}: ${d.count}`}>
                <span className="day-bar" style={{ height: `${(d.count / maxDay) * 100}%` }} />
                <span className="day-label">{new Date(d.date).getDate()}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <h3>What gets dropped</h3>
          {types.length === 0 && <p className="muted">Nothing detected yet.</p>}
          <ul className="bars">
            {types.map(([t, n]) => (
              <li key={t}>
                <span>{wasteLabel(t)}</span>
                <span className="bar"><span style={{ width: `${(n / maxType) * 100}%` }} /></span>
                <span className="num">{n}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h3>Latest detections</h3>
          <Link to="/violations">See all</Link>
        </div>
        {recent.length === 0 ? (
          <p className="muted">No detections yet. Upload a video on the Analyse footage page to try the detector.</p>
        ) : (
          <ul className="recent">
            {recent.map((v) => (
              <li key={v.id}>
                <Link to={`/violations/${v.id}`}>
                  <img src={mediaUrl(v.evidence_urls.scene)} alt="" loading="lazy" />
                  <span className="recent-main">
                    <span><strong>{wasteLabel(v.waste_type)}</strong> at {v.location || v.camera_id}</span>
                    <span className="muted">{timeAgo(v.detected_at)}</span>
                  </span>
                  <StatusTag status={v.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function Figure({ label, value }) {
  return (
    <div className="figure">
      <span className="figure-value num">{value}</span>
      <span className="figure-label">{label}</span>
    </div>
  );
}
