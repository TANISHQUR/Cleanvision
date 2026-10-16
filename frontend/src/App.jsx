import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { session } from "./api.js";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Overview from "./pages/Overview.jsx";
import Queue from "./pages/Queue.jsx";
import Review from "./pages/Review.jsx";
import Upload from "./pages/Upload.jsx";
import Challans from "./pages/Challans.jsx";
import Citizens from "./pages/Citizens.jsx";
import CitizenDetail from "./pages/CitizenDetail.jsx";

export default function App() {
  const [user, setUser] = useState(session.token ? session.user : null);

  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener("cleanvision:logout", onLogout);
    return () => window.removeEventListener("cleanvision:logout", onLogout);
  }, []);

  if (!user) return <Login onLogin={setUser} />;

  const logout = () => {
    session.clear();
    setUser(null);
  };

  return (
    <Layout user={user} onLogout={logout}>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/violations" element={<Queue />} />
        <Route path="/violations/:id" element={<Review />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/challans" element={<Challans />} />
        <Route path="/citizens" element={<Citizens />} />
        <Route path="/citizens/:id" element={<CitizenDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
