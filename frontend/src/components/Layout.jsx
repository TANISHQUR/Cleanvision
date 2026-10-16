import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api.js";

export default function Layout({ user, onLogout, children }) {
  const [pending, setPending] = useState(null);
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.stats().then((s) => alive && setPending(s.by_status.pending)).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [location.pathname]);

  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "is-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span>CleanVision</span>
          <button className="menu-toggle" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Menu">
            <span />
            <span />
          </button>
        </div>
        <nav className="nav">
          <NavLink to="/violations?status=pending" className={() => (location.pathname.startsWith("/violations") ? "active" : "")}>
            Review queue
            {pending > 0 && <span className="nav-count">{pending}</span>}
          </NavLink>
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/upload">Analyse footage</NavLink>
          <NavLink to="/challans">Challans</NavLink>
          <NavLink to="/citizens">Citizen registry</NavLink>
        </nav>
        <div className="sidebar-foot">
          <span>Signed in as {user}</span>
          <button className="link-button" onClick={onLogout}>Sign out</button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
