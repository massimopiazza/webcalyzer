import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Toaster } from "./components/Toaster";
import {
  CalibratePage,
  createDefaultCalibratePageState,
} from "./pages/CalibratePage";
import { DocumentationPage } from "./pages/DocumentationPage";
import { PostprocessingPage } from "./pages/PostprocessingPage";
import { QuantityLibraryPage } from "./pages/QuantityLibraryPage";
import { createDefaultRunPageState, RunPage } from "./pages/RunPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { api } from "./lib/api";

const LATEST_RUN_OUTPUT_KEY = "webcalyzer:latest-run-output";

export default function App() {
  const [runPageState, setRunPageState] = useState(createDefaultRunPageState);
  const [calibratePageState, setCalibratePageState] = useState(
    createDefaultCalibratePageState,
  );
  const [latestRunOutputDir, setLatestRunOutputDir] = useState(
    () => window.localStorage.getItem(LATEST_RUN_OUTPUT_KEY) ?? "",
  );

  useEffect(() => {
    const jobId = runPageState.activeJobId;
    if (!jobId) return;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const job = await api.job(jobId);
        if (cancelled) return;
        if (job.state === "succeeded") {
          window.localStorage.setItem(LATEST_RUN_OUTPUT_KEY, job.output_dir);
          setLatestRunOutputDir(job.output_dir);
          return;
        }
        if (job.state === "failed" || job.state === "cancelled") return;
      } catch {
        if (cancelled) return;
      }
      timer = window.setTimeout(poll, 1_000);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [runPageState.activeJobId]);

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
          <Route path="quantities" element={<QuantityLibraryPage />} />
          <Route
            path="postprocessing"
            element={<PostprocessingPage suggestedOutputDir={latestRunOutputDir} />}
          />
          <Route path="documentation" element={<DocumentationPage />} />
        </Route>
      </Routes>
      <Toaster />
    </>
  );
}
