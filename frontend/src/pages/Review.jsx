import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, mediaUrl } from "../api.js";
import CitizenPicker from "../components/CitizenPicker.jsx";
import { Confidence, ErrorNote, Loading, StatusTag } from "../components/ui.jsx";
import { formatDate, formatDateTime, formatMoney, formatSeconds, wasteLabel } from "../format.js";

export default function Review() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [v, setV] = useState(null);
  const [error, setError] = useState(null);
  const [citizen, setCitizen] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(null);
  const [done, setDone] = useState(null);

  useEffect(() => {
    setV(null);
    setError(null);
    setCitizen(null);
    setNote("");
    setDone(null);
    api.violation(id).then(setV).catch(setError);
  }, [id]);

  async function act(action) {
    setBusy(action);
    setError(null);
    try {
      const updated = await api.review(id, { action, note, citizen_id: citizen?.id });
      setV(updated);
      setDone(action);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function nextInQueue() {
    const res = await api.violations({ status: "pending", limit: 2 });
    const next = res.items.find((x) => x.id !== id);
    navigate(next ? `/violations/${next.id}` : "/violations?status=pending");
  }

  if (error && !v) return <ErrorNote error={error} />;
  if (!v) return <Loading />;

  const open = v.status === "pending" || v.status === "flagged";
  const urls = v.evidence_urls;

  return (
    <div className="review">
      <div className="review-top">
        <Link to="/violations" className="back">Back to queue</Link>
        <div className="review-title">
          <h1>{wasteLabel(v.waste_type)} left at {v.location || v.camera_id}</h1>
          <StatusTag status={v.status} />
        </div>
        <p className="muted num">{v.code}, detected {formatDateTime(v.detected_at)}</p>
      </div>

      <div className="review-grid">
        <section className="desk" aria-label="Evidence">
          {urls.clip ? (
            <video key={urls.clip} className="clip" src={mediaUrl(urls.clip)} controls autoPlay muted loop playsInline />
          ) : (
            <div className="clip clip-missing">No clip was saved for this incident.</div>
          )}
          <div className="stills">
            <figure>
              <img src={mediaUrl(urls.contact)} alt="Person with the object before it was dropped" />
              <figcaption>In hand</figcaption>
            </figure>
            <figure>
              <img src={mediaUrl(urls.scene)} alt="Object left on the ground" />
              <figcaption>Left behind</figcaption>
            </figure>
          </div>
          <p className="desk-note">
            Orange box: the person the detector linked to the object. Red box: the object.
          </p>
        </section>

        <aside className="case">
          <dl className="facts">
            <dt>Object</dt>
            <dd>{wasteLabel(v.waste_type)}</dd>
            <dt>Confidence</dt>
            <dd><Confidence value={v.confidence} /></dd>
            <dt>Camera</dt>
            <dd>{v.camera_id}</dd>
            <dt>Location</dt>
            <dd>{v.location || "Not set"}</dd>
            {v.source?.video_name && (
              <>
                <dt>Video</dt>
                <dd className="break">{v.source.video_name}{v.video_time != null && ` at ${formatSeconds(v.video_time)}`}</dd>
              </>
            )}
            <dt>Background check</dt>
            <dd>
              {v.verified_new === true && "Spot was clear before, object is new"}
              {v.verified_new === false && "Object may have been there already"}
              {v.verified_new == null && "No clear earlier frame to compare"}
            </dd>
          </dl>

          {v.review && (
            <div className="review-record">
              <p>
                {v.review.action === "approve" && "Approved"}
                {v.review.action === "reject" && "Dismissed"}
                {v.review.action === "flag" && "Marked for a second look"} by {v.review.by}, {formatDateTime(v.review.at)}
              </p>
              {v.review.note && <blockquote>{v.review.note}</blockquote>}
            </div>
          )}

          {v.status === "approved" && v.challan && (
            <div className="challan-card">
              <div className="challan-row">
                <span className="muted">Challan</span>
                <strong className="num">{v.challan.number}</strong>
              </div>
              <div className="challan-row">
                <span className="muted">Issued to</span>
                <Link to={`/citizens/${v.citizen.id}`}>{v.citizen.name}</Link>
              </div>
              <div className="challan-row">
                <span className="muted">Amount</span>
                <strong className="num">{formatMoney(v.challan.amount)}</strong>
              </div>
              <div className="challan-row">
                <span className="muted">Due</span>
                <span className="num">{formatDate(v.challan.due_date)}</span>
              </div>
              <div className="challan-row">
                <span className="muted">Payment</span>
                <span className={`pay pay-${v.challan.status}`}>{v.challan.status === "issued" ? "unpaid" : v.challan.status}</span>
              </div>
            </div>
          )}

          {open && (
            <form className="decide stack" onSubmit={(e) => e.preventDefault()}>
              <h2>Your decision</h2>
              <CitizenPicker value={citizen} onChange={setCitizen} />
              <label className="field">
                <span>Note (optional)</span>
                <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder="What you saw in the clip" maxLength={1000} />
              </label>
              <ErrorNote error={error} />
              <button type="button" className="btn btn-primary" disabled={!citizen || busy}
                onClick={() => act("approve")}>
                {busy === "approve" ? "Issuing…" : "Approve and issue challan"}
              </button>
              {!citizen && <p className="hint">Pick the person in the clip to issue a challan.</p>}
              <div className="btn-row">
                {v.status === "pending" && (
                  <button type="button" className="btn" disabled={busy} onClick={() => act("flag")}>
                    {busy === "flag" ? "Saving…" : "Needs a second look"}
                  </button>
                )}
                <button type="button" className="btn btn-danger" disabled={busy} onClick={() => act("reject")}>
                  {busy === "reject" ? "Saving…" : "Dismiss"}
                </button>
              </div>
            </form>
          )}

          {done && (
            <div className="done">
              <p>
                {done === "approve" && "Challan issued."}
                {done === "reject" && "Incident dismissed."}
                {done === "flag" && "Marked for a second look."}
              </p>
              <button className="btn btn-primary" onClick={nextInQueue}>Next incident</button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
