import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Toaster } from "./components/Toaster";
import {
  CalibratePage,
  createDefaultCalibratePageState,
} from "./pages/CalibratePage";
import { DocumentationPage } from "./pages/DocumentationPage";
import { createDefaultRunPageState, RunPage } from "./pages/RunPage";
import { TemplatesPage } from "./pages/TemplatesPage";

export default function App() {
  const [runPageState, setRunPageState] = useState(createDefaultRunPageState);
  const [calibratePageState, setCalibratePageState] = useState(
    createDefaultCalibratePageState,
  );

  return (
    <>
      <Routes>
        <Route element={<AppShell />}>
          <Route
            index
            element={
              <RunPage
                persistedState={runPageState}
                onPersistedStateChange={setRunPageState}
              />
            }
          />
          <Route
            path="calibrate"
            element={
              <CalibratePage
                persistedState={calibratePageState}
                onPersistedStateChange={setCalibratePageState}
              />
            }
          />
          <Route path="templates" element={<TemplatesPage />} />
          <Route path="documentation" element={<DocumentationPage />} />
        </Route>
      </Routes>
      <Toaster />
    </>
  );
}
