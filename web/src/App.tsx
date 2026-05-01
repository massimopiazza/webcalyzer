import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Toaster } from "./components/Toaster";
import { CalibratePage } from "./pages/CalibratePage";
import { RunPage } from "./pages/RunPage";
import { TemplatesPage } from "./pages/TemplatesPage";

export default function App() {
  return (
    <>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<RunPage />} />
          <Route path="calibrate" element={<CalibratePage />} />
          <Route path="templates" element={<TemplatesPage />} />
        </Route>
      </Routes>
      <Toaster />
    </>
  );
}
