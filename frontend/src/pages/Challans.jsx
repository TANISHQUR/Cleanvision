import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Empty, ErrorNote, Loading, PageHeader } from "../components/ui.jsx";
import { formatDate, formatMoney, wasteLabel } from "../format.js";

const FILTERS = [
  ["", "All"],
  ["issued", "Unpaid"],
  ["paid", "Paid"],
  ["cancelled", "Cancelled"],
];

export default function Challans() {
  const [status, setStatus] = useState("");
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  const load = () => api.challans(status).then((r) => setItems(r.items)).catch(setError);
  useEffect(() => {
    setItems(null);
    load();
  }, [status]);

  async function update(id, next) {
    if (next === "cancelled" && !window.confirm("Cancel this challan? This can't be undone.")) return;
    try {
      await api.updateChallan(id, next);
      load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageHeader title="Challans" lead="Fines issued from approved incidents. Payments are simulated in this prototype." />
      <div className="tabs">
        {FILTERS.map(([k, label]) => (
          <button key={k || "all"} className={status === k ? "tab active" : "tab"} onClick={() => setStatus(k)}>{label}</button>
        ))}
      </div>
      <ErrorNote error={error} />
      {!items ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty title="No challans here">
          <p>Approving an incident in the review queue issues a challan.</p>
        </Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Challan</th>
                <th>Issued to</th>
                <th>For</th>
                <th className="right">Amount</th>
                <th>Due</th>
                <th>Payment</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td className="num"><strong>{c.number}</strong><div className="muted">{formatDate(c.issued_at)}</div></td>
                  <td><Link to={`/citizens/${c.citizen_id}`}>{c.citizen_name}</Link></td>
                  <td>
                    <Link to={`/violations/${c.violation_id}`}>{wasteLabel(c.waste_type)}</Link>
                    <div className="muted num">{c.violation_code}</div>
                  </td>
                  <td className="num right">{formatMoney(c.amount)}</td>
                  <td className="num">{formatDate(c.due_date)}</td>
                  <td><span className={`pay pay-${c.status}`}>{c.status === "issued" ? "unpaid" : c.status}</span></td>
                  <td>
                    {c.status === "issued" && (
                      <div className="actions">
                        <button className="btn btn-small" onClick={() => update(c.id, "paid")}>Mark paid</button>
                        <button className="link-button danger" onClick={() => update(c.id, "cancelled")}>Cancel</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
