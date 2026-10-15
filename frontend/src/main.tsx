import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import PatientDetailPage from "./pages/PatientDetailPage";
import DashboardPage from "./pages/DashboardPage";
import { LiveUpdatesProvider } from "./components/LiveUpdates";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <LiveUpdatesProvider>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/patients/:id" element={<PatientDetailPage />} />
          <Route path="*" element={<DashboardPage />} />
        </Routes>
      </LiveUpdatesProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
