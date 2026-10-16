import { useState } from "react";
import { api, session } from "../api.js";
import { ErrorNote } from "../components/ui.jsx";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(username, password);
      session.save(res.token, res.username);
      onLogin(res.username);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-panel">
        <div className="brand brand-large">
          <span className="brand-mark" aria-hidden="true" />
          <span>CleanVision</span>
        </div>
        <p className="lead">Review littering incidents picked up by your cameras and issue challans.</p>
        <form onSubmit={submit} className="stack">
          <label className="field">
            <span>Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </label>
          <label className="field">
            <span>Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" required autoFocus />
          </label>
          <ErrorNote error={error} />
          <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </div>
    </div>
  );
}
