import { Route, Routes } from "react-router-dom";
import { AdminPage } from "./pages/AdminPage";
import { RadioPage } from "./pages/RadioPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<RadioPage />} />
      <Route path="/studio" element={<AdminPage />} />
      <Route path="*" element={<RadioPage />} />
    </Routes>
  );
}
