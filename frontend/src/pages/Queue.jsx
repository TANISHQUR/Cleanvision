import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, mediaUrl } from "../api.js";
import { Confidence, Empty, ErrorNote, Loading, PageHeader, StatusTag } from "../components/ui.jsx";
import { formatDateTime, wasteLabel, WASTE_LABELS } from "../format.js";

const TABS = [
  ["pending", "Waiting"],
  ["flagged", "Second look"],
  ["approved", "Challan issued"],
  ["rejected", "Dismissed"],
  ["", "All"],
];
const PAGE = 25;

export default function Queue() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "pending";
  const wasteType = params.get("waste_type") || "";
  const jobId = params.get("job_id") || "";
  const page = Number(params.get("page") || 0);
  const [data, setData] = useState(null);
  const [counts, setCounts] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    setData(null);
    api.violations({ status, waste_type: wasteType, job_id: jobId, limit: PAGE, skip: page * PAGE })
      .then(setData)
      .catch(setError);
  }, [status, wasteType, jobId, page]);

  useEffect(() => {
    api.stats().then((s) => setCounts({ ...s.by_status, "": s.total })).catch(() => {});
  }, [status]);

  const set = (patch) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v === "" || v === null ? next.delete(k) : next.set(k, v)));
    if (!("page" in patch)) next.delete("page");
    if ("status" in patch && patch.status === "") next.set("status", "");
    setParams(next);
  };

  return (
    <>
      <PageHeader title="Review queue">
        <label className="field field-inline">
          <span>Waste type</span>
          <select value={wasteType} onChange={(e) => set({ waste_type: e.target.value })}>
            <option value="">Any</option>
            {Object.entries(WASTE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
      </PageHeader>

      {jobId && (
        <p className="filter-note">
          Showing detections from one uploaded video. <button className="link-button" onClick={() => set({ job_id: "" })}>Show everything</button>
        </p>
      )}

      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key || "all"} role="tab" aria-selected={status === key}
            className={status === key ? "tab active" : "tab"} onClick={() => set({ status: key })}>
            {label}
            {counts && <span className="tab-count num">{counts[key] ?? 0}</span>}
          </button>
        ))}
      </div>

      <ErrorNote error={error} />
      {!data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <Empty title={status === "pending" ? "Nothing waiting for review" : "No incidents here"}>
          {status === "pending" && (
            <p>New detections appear here as the detector finds them. <Link to="/upload">Analyse a video</Link> to create some.</p>
          )}
        </Empty>
      ) : (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Evidence</th>
                  <th>Incident</th>
                  <th>Where</th>
                  <th>When</th>
                  <th>Confidence</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((v) => (
                  <tr key={v.id} className="row-link" tabIndex={0}
                    onClick={() => navigate(`/violations/${v.id}`)}
                    onKeyDown={(e) => e.key === "Enter" && navigate(`/violations/${v.id}`)}>
                    <td><img className="thumb" src={mediaUrl(v.evidence_urls.scene)} alt="" loading="lazy" /></td>
                    <td>
                      <strong>{wasteLabel(v.waste_type)}</strong>
                      <div className="muted num">{v.code}</div>
                    </td>
                    <td>
                      {v.location || "Unknown location"}
                      <div className="muted">{v.camera_id}</div>
                    </td>
                    <td className="num">{formatDateTime(v.detected_at)}</td>
                    <td><Confidence value={v.confidence} /></td>
                    <td><StatusTag status={v.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span className="muted num">
              {page * PAGE + 1}–{page * PAGE + data.items.length} of {data.total}
            </span>
            <button className="btn btn-small" disabled={page === 0} onClick={() => set({ page: page - 1 })}>Previous</button>
            <button className="btn btn-small" disabled={(page + 1) * PAGE >= data.total} onClick={() => set({ page: page + 1 })}>Next</button>
          </div>
        </>
      )}
    </>
  );
}
