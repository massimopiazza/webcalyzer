import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Toaster } from "./components/Toaster";
import {
  CalibratePage,
  createDefaultCalibratePageState,
} from "./pages/CalibratePage";
import { DocumentationPage } from "./pages/DocumentationPage";
import { QuantityLibraryPage } from "./pages/QuantityLibraryPage";
import {
  createDefaultPostprocessingPageState,
  PostprocessingPage,
} from "./pages/PostprocessingPage";
import { createDefaultRunPageState, RunPage } from "./pages/RunPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { api } from "./lib/api";

const LATEST_RUN_OUTPUT_KEY = "webcalyzer:latest-run-output";

export default function App() {
  const initialLatestRunOutputDir =
    window.localStorage.getItem(LATEST_RUN_OUTPUT_KEY) ?? "";
  const [runPageState, setRunPageState] = useState(createDefaultRunPageState);
  const [calibratePageState, setCalibratePageState] = useState(
    createDefaultCalibratePageState,
  );
  const [postprocessingPageState, setPostprocessingPageState] = useState(() =>
    createDefaultPostprocessingPageState(initialLatestRunOutputDir),
  );
  const [latestRunOutputDir, setLatestRunOutputDir] = useState(
    initialLatestRunOutputDir,
  );

  useEffect(() => {
    const workspace = postprocessingPageState.workspace;
    if (!workspace) return;
    const timer = window.setInterval(() => {
      api
        .postprocessingHeartbeat(workspace.path, workspace.session_token)
        .then((draft) => {
          setPostprocessingPageState((current) => {
            if (
              !current.workspace ||
              current.workspace.path !== workspace.path ||
              current.workspace.session_token !== workspace.session_token
            ) {
              return current;
            }
            return {
              ...current,
              workspace: {
                ...current.workspace,
                draft,
              },
            };
          });
        })
        .catch(() => null);
    }, 20_000);
    return () => window.clearInterval(timer);
  }, [
    postprocessingPageState.workspace?.path,
    postprocessingPageState.workspace?.session_token,
  ]);

  useEffect(() => {
    const jobId = runPageState.activeJobId;
    if (!jobId) return;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const job = await api.job(jobId);
        if (cancelled) return;
        const postprocessingReady =
          job.state === "succeeded" || job.outputs.includes("config_resolved.yaml");
        if (postprocessingReady) {
          window.localStorage.setItem(LATEST_RUN_OUTPUT_KEY, job.output_dir);
          setLatestRunOutputDir(job.output_dir);
          setPostprocessingPageState((current) =>
            current.workspace
              ? current
              : current.outputDir === job.output_dir
                ? current
                : { ...current, outputDir: job.output_dir },
          );
        }
        if (job.state === "succeeded") {
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
            element={
              <PostprocessingPage
                persistedState={postprocessingPageState}
                onPersistedStateChange={setPostprocessingPageState}
                suggestedOutputDir={latestRunOutputDir}
              />
            }
          />
          <Route path="documentation" element={<DocumentationPage />} />
        </Route>
      </Routes>
      <Toaster />
    </>
  );
}
