const dateFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" });
const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

export const formatDate = (iso) => (iso ? dateFmt.format(new Date(iso)) : "");
export const formatDateTime = (iso) => (iso ? `${dateFmt.format(new Date(iso))}, ${timeFmt.format(new Date(iso))}` : "");
export const formatMoney = (n) => money.format(n || 0);
export const formatPercent = (x) => `${Math.round((x || 0) * 100)}%`;
export const formatSeconds = (s) => {
  if (s === null || s === undefined) return "";
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
};

export const WASTE_LABELS = {
  bottle: "Bottle",
  can: "Can",
  wrapper: "Wrapper",
  paper: "Paper",
  cup: "Cup",
};
export const wasteLabel = (w) => WASTE_LABELS[w] || (w ? w[0].toUpperCase() + w.slice(1) : "Unknown");

export const STATUS_LABELS = {
  pending: "Waiting for review",
  flagged: "Second look",
  approved: "Challan issued",
  rejected: "Dismissed",
};

export function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return formatDate(iso);
}
