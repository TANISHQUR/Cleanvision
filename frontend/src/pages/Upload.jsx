import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Empty, ErrorNote, PageHeader } from "../components/ui.jsx";
import { timeAgo } from "../format.js";

const ACTIVE = ["queued", "starting", "running"];
const JOB_LABELS = {
  queued: "In line",
  starting: "Starting",
  running: "Analysing",
  completed: "Finished",
  failed: "Failed",
};

export default function Upload() {
  const [file, setFile] = useState(null);
  const [cameraId, setCameraId] = useState("CAM-01");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [jobs, setJobs] = useState([]);
  const inputRef = useRef(null);

  const load = () => api.jobs().then((r) => setJobs(r.items)).catch(setError);

  useEffect(() => {
    load();
  }, []);

  const anyActive = jobs.some((j) => ACTIVE.includes(j.status));
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [anyActive]);

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("video", file);
    form.append("camera_id", cameraId);
    form.append("location", location);
    try {
      await api.uploadVideo(form);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Analyse footage"
        lead="Upload a recording and the detector will look for littering. Anything it finds goes to the review queue." />

      <form className="panel upload-form" onSubmit={submit}>
        <label className={`drop ${file ? "has-file" : ""}`}>
          <input ref={inputRef} type="file" accept="video/*" onChange={(e) => setFile(e.target.files[0] || null)} />
          {file ? (
            <>
              <strong>{file.name}</strong>
              <span className="muted num">{(file.size / 1024 / 1024).toFixed(1)} MB. Click to choose a different file.</span>
            </>
          ) : (
            <>
              <strong>Choose a video file</strong>
              <span className="muted">MP4, MOV, AVI, MKV or WebM</span>
            </>
          )}
        </label>
        <div className="form-row">
          <label className="field">
            <span>Camera ID</span>
            <input value={cameraId} onChange={(e) => setCameraId(e.target.value)} maxLength={40} required />
          </label>
          <label className="field grow">
            <span>Location</span>
            <input value={location} onChange={(e) => setLocation(e.target.value)} maxLength={200}
              placeholder="e.g. Metro exit gate 2, Pitampura" />
          </label>
        </div>
        <ErrorNote error={error} />
        <div>
          <button className="btn btn-primary" disabled={!file || busy}>{busy ? "Uploading…" : "Upload and analyse"}</button>
        </div>
      </form>

      <section className="panel">
        <h3>Recent uploads</h3>
        {jobs.length === 0 ? (
          <Empty title="No videos analysed yet" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Video</th>
                  <th>Camera</th>
                  <th>Progress</th>
                  <th>Found</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td className="break">
                      {j.video_name}
                      {j.error && <div className="error-text">{j.error}</div>}
                    </td>
                    <td>{j.camera_id}</td>
                    <td>
                      <div className={`job job-${j.status}`}>
                        <span className="job-bar"><span style={{ width: `${Math.round((j.progress || 0) * 100)}%` }} /></span>
                        <span>{JOB_LABELS[j.status] || j.status}{j.status === "running" && ` ${Math.round(j.progress * 100)}%`}</span>
                      </div>
                    </td>
                    <td className="num">
                      {j.violations > 0 ? (
                        <Link to={`/violations?status=&job_id=${j.id}`}>{j.violations} incident{j.violations > 1 ? "s" : ""}</Link>
                      ) : j.status === "completed" ? "None" : ""}
                    </td>
                    <td className="muted">{timeAgo(j.created_at)}</td>
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
