export type FileEntry = {
  name: string;
  path: string;
  type: "dir" | "file" | "video";
  size: number;
  modified: number;
};

export type FileListing = {
  path: string;
  parent: string | null;
  entries: FileEntry[];
};

export type Meta = {
  version: string;
  roots: { label: string; path: string }[];
  templates_dir: string;
  quantity_library_dir: string;
  units: string[];
  trajectory: {
    interpolation_methods: string[];
    integration_methods: string[];
  };
  default_parsing: ParsingDTO;
  dimensions: {
    bases: { symbol: string; label: string }[];
    presets: Record<string, string>;
    preset_units: Record<string, string>;
  };
};

export type TemplateSummary = {
  name: string;
  profile_name: string;
  description: string;
  modified: number;
  size: number;
  error: string | null;
};

export type FieldDTO = {
  kind: "velocity" | "altitude" | "met" | "custom";
  stage: "stage1" | "stage2" | null;
  quantity_id?: string | null;
  bbox_x1y1x2y2: [number, number, number, number] | null;
};

export type CalibrationVideoDTO = {
  path: string | null;
  fps: number | null;
  frame_count: number | null;
  width: number | null;
  height: number | null;
};

export type SegmentDTO = {
  id: string;
  start_frame_index: number;
  start_time_s: number;
  end_frame_index: number;
  end_time_s: number;
  visible_fields: string[];
  fields: Record<string, FieldDTO>;
};

export type LaunchSiteDTO = {
  latitude_deg: number | null;
  longitude_deg: number | null;
  azimuth_deg: number | null;
};

export type TrajectoryDTO = {
  enabled: boolean;
  interpolation_method: string;
  integration_method: string;
  outlier_rejection_enabled: boolean;
  outlier_rejection_chi2_threshold: number;
  outlier_rejection_window_s: number;
  outlier_preconditioning_enabled: boolean;
  coarse_step_smoothing_enabled: boolean;
  coarse_step_max_gap_s: number;
  coarse_altitude_threshold_m: number;
  coarse_velocity_threshold_mps: number;
  acceleration_source_gap_threshold_s: number;
  derivative_smoothing_window_s: number;
  derivative_smoothing_polyorder: number;
  derivative_min_window_samples: number;
  derivative_smoothing_mode: string;
  launch_site: LaunchSiteDTO;
};

export type VideoOverlayDTO = {
  enabled: boolean;
  plot_mode: "filtered" | "with_rejected";
  engine: "auto" | "ffmpeg" | "opencv";
  encoder:
    | "auto"
    | "videotoolbox"
    | "h264_videotoolbox"
    | "nvenc"
    | "h264_nvenc"
    | "qsv"
    | "h264_qsv"
    | "vaapi"
    | "h264_vaapi"
    | "libx264";
  width_fraction: number;
  height_fraction: number;
  output_filename: string;
  include_audio: boolean;
};

export type UnitAliasDTO = {
  aliases: string[];
  unit: string;
};

export type FieldKindParsingDTO = {
  units: Record<string, UnitAliasDTO>;
  default_unit: string;
  ambiguous_default_unit: string | null;
  inferred_units_with_separator: string[];
  inferred_units_without_separator: string[];
  output_unit: string | null;
};

export type MetParsingDTO = {
  timestamp_patterns: string[];
};

export type ParsingDTO = {
  velocity: FieldKindParsingDTO;
  altitude: FieldKindParsingDTO;
  met: MetParsingDTO;
  custom_words: string[];
};

export type HardcodedStageDTO = {
  velocity_mps: number | null;
  altitude_m: number | null;
};

export type HardcodedRawPointDTO = {
  mission_elapsed_time_s: number;
  stage1: HardcodedStageDTO;
  stage2: HardcodedStageDTO;
  custom_values: Record<string, number>;
};

export type QuantityDTO = {
  id: string;
  name: string;
  slug: string;
  dimensionality: string;
  display_unit: string;
  description: string;
  unit_aliases: Record<string, string>;
  is_default?: boolean;
  field_name?: string;
};

export type ProfileDTO = {
  profile_name: string;
  description: string;
  default_sample_fps: number;
  default_ocr_workers: number;
  ocr_backend: "auto" | "rapidocr" | "vision";
  ocr_recognition_level: "accurate" | "fast";
  skip_full_frame_ocr_fallback: boolean;
  fixture_frame_count: number;
  fixture_time_range_s: [number, number] | null;
  calibration_video: CalibrationVideoDTO;
  video_overlay: VideoOverlayDTO;
  trajectory: TrajectoryDTO;
  parsing: ParsingDTO | null;
  custom_telemetry_quantities: QuantityDTO[];
  hardcoded_raw_data_points: HardcodedRawPointDTO[];
  segments: SegmentDTO[];
};

export type JobSummary = {
  id: string;
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  started_at: number;
  ended_at: number | null;
  error: string | null;
  video_path: string;
  output_dir: string;
  profile_name: string;
  outputs: string[];
};

export type JobEvent = {
  kind: "log" | "phase" | "progress" | "done" | "error" | "cancelled";
  message: string;
  payload: Record<string, unknown>;
  timestamp: number;
};

export type VideoMetadata = {
  path: string;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  duration_s: number;
};

export type FixtureFrames = {
  video: VideoMetadata;
  frames: { index: number; time_s: number }[];
};

const BASE = "";

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(status: number, message: string, details: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      try {
        body = await response.text();
      } catch {
        /* ignore */
      }
    }
    const message =
      typeof body === "object" && body !== null && "detail" in body
        ? typeof (body as { detail: unknown }).detail === "string"
          ? ((body as { detail: string }).detail)
          : `HTTP ${response.status}`
        : `HTTP ${response.status}`;
    throw new ApiError(response.status, message, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  files: (path?: string, kinds?: string) => {
    const params = new URLSearchParams();
    if (path) params.set("path", path);
    if (kinds) params.set("kinds", kinds);
    const qs = params.toString();
    return request<FileListing>(`/api/files${qs ? `?${qs}` : ""}`);
  },
  videoMetadata: (path: string) =>
    request<VideoMetadata>(`/api/video/metadata?path=${encodeURIComponent(path)}`),
  fixtureFrames: (path: string, count: number, startS: number | null, endS: number | null) => {
    const params = new URLSearchParams({ path, count: String(count) });
    if (startS !== null) params.set("start_s", String(startS));
    if (endS !== null) params.set("end_s", String(endS));
    return request<FixtureFrames>(`/api/video/fixture-frames?${params.toString()}`);
  },
  templates: () => request<TemplateSummary[]>("/api/templates"),
  template: (name: string) =>
    request<{ name: string; profile: ProfileDTO }>(`/api/templates/${encodeURI(name)}`),
  saveTemplate: (name: string, profile: ProfileDTO) =>
    request<{ name: string; path: string }>(`/api/templates/${encodeURI(name)}`, {
      method: "PUT",
      body: JSON.stringify(profile),
    }),
  deleteTemplate: (name: string) =>
    request<{ name: string; deleted: boolean }>(`/api/templates/${encodeURI(name)}`, {
      method: "DELETE",
    }),
  duplicateTemplate: (sourceName: string, fileName: string) =>
    request<{ name: string; path: string }>(`/api/templates/${encodeURI(sourceName)}/duplicate`, {
      method: "POST",
      body: JSON.stringify({ name: fileName }),
    }),
  importTemplate: (name: string, yamlText: string) =>
    request<{ name: string; profile: ProfileDTO }>(`/api/templates/import`, {
      method: "POST",
      body: JSON.stringify({ name, yaml: yamlText }),
    }),
  templateYaml: async (name: string) => {
    const response = await fetch(`/api/templates/${encodeURI(name)}/yaml`);
    if (!response.ok) {
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        try {
          body = await response.text();
        } catch {
          /* ignore */
        }
      }
      const message =
        typeof body === "object" && body !== null && "detail" in body
          ? typeof (body as { detail: unknown }).detail === "string"
            ? ((body as { detail: string }).detail)
            : `HTTP ${response.status}`
          : `HTTP ${response.status}`;
      throw new ApiError(response.status, message, body);
    }
    return await response.text();
  },
  templateYamlUrl: (name: string) => `/api/templates/${encodeURI(name)}/yaml`,
  quantities: () => request<{ path: string; quantities: QuantityDTO[] }>("/api/quantities"),
  createQuantity: (quantity: Partial<QuantityDTO>) =>
    request<{ quantity: QuantityDTO; quantities: QuantityDTO[] }>("/api/quantities", {
      method: "POST",
      body: JSON.stringify(quantity),
    }),
  updateQuantity: (id: string, quantity: Partial<QuantityDTO>) =>
    request<{ quantity: QuantityDTO; quantities: QuantityDTO[] }>(`/api/quantities/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(quantity),
    }),
  deleteQuantity: (id: string) =>
    request<{ id: string; deleted: boolean; quantities: QuantityDTO[] }>(`/api/quantities/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  quantityUsage: (id: string, profile?: ProfileDTO) =>
    request<{ id: string; usage: { template: string; profile_name: string; categories: string[] }[] }>(
      `/api/quantities/${encodeURIComponent(id)}/usage`,
      {
        method: "POST",
        body: JSON.stringify({ profile }),
      },
    ),
  normalizeDimension: (expression: string) =>
    request<{ normalized: string }>("/api/dimensions/normalize", {
      method: "POST",
      body: JSON.stringify({ expression }),
    }),
  unitSuggestions: (prefix: string) =>
    request<{ suggestions: string[] }>(`/api/units/suggestions?prefix=${encodeURIComponent(prefix)}`),
  siUnit: (dimensionality: string) =>
    request<{ unit: string; dimensionality: string }>(
      `/api/units/si?dimensionality=${encodeURIComponent(dimensionality)}`,
    ),
  validateProfile: (profile: ProfileDTO) =>
    request<{ profile: ProfileDTO }>("/api/profile/validate-draft", {
      method: "POST",
      body: JSON.stringify(profile),
    }),
  validateRunnableProfile: (profile: ProfileDTO) =>
    request<{ profile: ProfileDTO }>("/api/profile/validate-runnable", {
      method: "POST",
      body: JSON.stringify(profile),
    }),
  previewYaml: async (profile: ProfileDTO) => {
    const response = await fetch("/api/profile/preview-yaml", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(profile),
    });
    if (!response.ok) {
      let detail: unknown = null;
      try {
        detail = await response.json();
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, `HTTP ${response.status}`, detail);
    }
    return await response.text();
  },
  videoFrameUrl: (path: string, timeS: number, maxWidth = 1280) =>
    `/api/video/frame?path=${encodeURIComponent(path)}&time_s=${timeS}&max_width=${maxWidth}`,
  videoFrameByIndexUrl: (path: string, index: number, maxWidth = 1280) =>
    `/api/video/frame-by-index?path=${encodeURIComponent(path)}&index=${index}&max_width=${maxWidth}`,
  saveCalibration: (template: string, profile: ProfileDTO) =>
    request<{ name: string; path: string }>("/api/calibrate/save", {
      method: "POST",
      body: JSON.stringify({ template, profile }),
    }),
  jobs: () => request<JobSummary[]>("/api/jobs"),
  runJob: (payload: {
    video_path: string;
    output_dir: string;
    template_name?: string | null;
    profile: ProfileDTO;
    sample_fps?: number | null;
    ocr_backend?: string;
    ocr_recognition_level?: string;
    ocr_workers?: number;
    ocr_skip_detection?: boolean;
    overlay_engine?: string;
    overlay_encoder?: string;
  }) =>
    request<{ id: string; state: string }>("/api/jobs/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  job: (id: string) =>
    request<JobSummary & { events: JobEvent[] }>(`/api/jobs/${id}`),
  cancelJob: (id: string) =>
    request<{ ok: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  jobFileUrl: (id: string, relpath: string) => `/api/jobs/${id}/files/${encodeURI(relpath)}`,
};
