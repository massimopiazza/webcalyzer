import userIndexMd from "../../../docs/user/index.md?raw";
import gettingStartedMd from "../../../docs/user/getting-started.md?raw";
import runExtractionMd from "../../../docs/user/run-extraction.md?raw";
import calibrationMd from "../../../docs/user/calibration.md?raw";
import templatesMd from "../../../docs/user/templates.md?raw";
import profileConfigurationMd from "../../../docs/user/profile-configuration.md?raw";
import trajectoryReconstructionMd from "../../../docs/user/trajectory-reconstruction.md?raw";
import outputsReviewMd from "../../../docs/user/outputs-and-review.md?raw";
import cliReferenceMd from "../../../docs/user/cli-reference.md?raw";

import internalIndexMd from "../../../docs/internal/index.md?raw";
import architectureMd from "../../../docs/internal/architecture.md?raw";
import configModelMd from "../../../docs/internal/config-model.md?raw";
import pipelineMd from "../../../docs/internal/pipeline.md?raw";
import webBackendMd from "../../../docs/internal/web-backend.md?raw";
import webFrontendMd from "../../../docs/internal/web-frontend.md?raw";
import fileMapMd from "../../../docs/internal/file-map.md?raw";
import functionIndexMd from "../../../docs/internal/function-index.md?raw";

export type DocsPage = {
  id: string;
  title: string;
  content: string;
};

export type DocsGroup = {
  id: "user" | "internal";
  label: string;
  pages: DocsPage[];
};

export const DOC_GROUPS: DocsGroup[] = [
  {
    id: "user",
    label: "User guide",
    pages: [
      { id: "index", title: "Overview", content: userIndexMd },
      { id: "getting-started", title: "Getting Started", content: gettingStartedMd },
      { id: "run-extraction", title: "Run Extraction", content: runExtractionMd },
      { id: "calibration", title: "Calibration", content: calibrationMd },
      { id: "templates", title: "Templates", content: templatesMd },
      { id: "profile-configuration", title: "Profile Configuration", content: profileConfigurationMd },
      { id: "trajectory-reconstruction", title: "Trajectory Reconstruction", content: trajectoryReconstructionMd },
      { id: "outputs-and-review", title: "Outputs and Review", content: outputsReviewMd },
      { id: "cli-reference", title: "CLI Reference", content: cliReferenceMd },
    ],
  },
  {
    id: "internal",
    label: "Internal",
    pages: [
      { id: "index", title: "Overview", content: internalIndexMd },
      { id: "architecture", title: "Architecture", content: architectureMd },
      { id: "config-model", title: "Configuration Model", content: configModelMd },
      { id: "pipeline", title: "Pipeline", content: pipelineMd },
      { id: "web-backend", title: "Web Backend", content: webBackendMd },
      { id: "web-frontend", title: "Web Frontend", content: webFrontendMd },
      { id: "file-map", title: "File Map", content: fileMapMd },
      { id: "function-index", title: "Function Index", content: functionIndexMd },
    ],
  },
];
