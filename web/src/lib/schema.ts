import { z } from "zod";

const IDENTIFIER = /^[A-Za-z0-9._\- ]+$/;

export const CANONICAL_FIELD_ORDER = [
  "met",
  "stage1_velocity",
  "stage1_altitude",
  "stage2_velocity",
  "stage2_altitude",
] as const;

export type CanonicalFieldName = (typeof CANONICAL_FIELD_ORDER)[number];

export const CANONICAL_FIELD_DEFINITIONS: Record<
  CanonicalFieldName,
  { kind: "velocity" | "altitude" | "met"; stage: "stage1" | "stage2" | null }
> = {
  met: { kind: "met", stage: null },
  stage1_velocity: { kind: "velocity", stage: "stage1" },
  stage1_altitude: { kind: "altitude", stage: "stage1" },
  stage2_velocity: { kind: "velocity", stage: "stage2" },
  stage2_altitude: { kind: "altitude", stage: "stage2" },
};

export const launchSiteSchema = z.object({
  latitude_deg: z.number().min(-90).max(90).nullable(),
  longitude_deg: z.number().min(-180).max(180).nullable(),
  azimuth_deg: z.number().min(0).max(360).nullable(),
});

export const trajectorySchema = z.object({
  enabled: z.boolean(),
  interpolation_method: z.string().min(1),
  integration_method: z.string().min(1),
  outlier_rejection_enabled: z.boolean(),
  outlier_rejection_chi2_threshold: z.number().positive(),
  outlier_rejection_window_s: z.number().positive(),
  outlier_preconditioning_enabled: z.boolean(),
  coarse_step_smoothing_enabled: z.boolean(),
  coarse_step_max_gap_s: z.number().positive(),
  coarse_altitude_threshold_m: z.number().min(0),
  coarse_velocity_threshold_mps: z.number().min(0),
  acceleration_source_gap_threshold_s: z.number().positive(),
  derivative_smoothing_window_s: z.number().positive(),
  derivative_smoothing_polyorder: z.number().int().min(0).max(10),
  derivative_min_window_samples: z.number().int().min(2).max(1000),
  derivative_smoothing_mode: z.enum(["interp", "nearest", "mirror", "constant", "wrap"]),
  launch_site: launchSiteSchema,
});

export const videoOverlaySchema = z.object({
  enabled: z.boolean(),
  plot_mode: z.enum(["filtered", "with_rejected"]),
  engine: z.enum(["auto", "ffmpeg", "opencv"]),
  encoder: z.enum([
    "auto",
    "videotoolbox",
    "h264_videotoolbox",
    "nvenc",
    "h264_nvenc",
    "qsv",
    "h264_qsv",
    "vaapi",
    "h264_vaapi",
    "libx264",
  ]),
  width_fraction: z.number().min(0.05).max(1),
  height_fraction: z.number().min(0.05).max(1),
  output_filename: z
    .string()
    .min(1)
    .max(255)
    .refine((v) => !v.includes("/") && !v.includes("\\"), {
      message: "Must be a bare filename",
    }),
  include_audio: z.boolean(),
});

export const fieldSchema = z
  .object({
    kind: z.enum(["velocity", "altitude", "met", "custom"]),
    stage: z.enum(["stage1", "stage2"]).nullable(),
    quantity_id: z.string().nullable().optional(),
    bbox_x1y1x2y2: z
      .tuple([z.number(), z.number(), z.number(), z.number()])
      .refine((box) => box.every((v) => v >= 0 && v <= 1), {
        message: "bbox values must be normalized 0..1",
      })
      .refine(([x0, y0, x1, y1]) => x1 > x0 && y1 > y0, {
        message: "bbox must satisfy x1>x0 and y1>y0",
      })
      .nullable(),
  })
  .superRefine((value, ctx) => {
    if (value.kind === "met" && value.stage !== null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["stage"],
        message: "Time fields must not have a stage",
      });
    }
    if (value.kind === "custom") {
      if (value.stage !== null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["stage"],
          message: "Custom fields must not have a stage",
        });
      }
      if (!value.quantity_id) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["quantity_id"],
          message: "Custom fields must reference a quantity",
        });
      }
    }
    if (value.kind !== "met" && value.kind !== "custom" && value.stage === null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["stage"],
        message: "Stage is required for velocity/altitude fields",
      });
    }
  });

export const calibrationVideoSchema = z.object({
  path: z.string().nullable(),
  fps: z.number().positive().nullable(),
  frame_count: z.number().int().min(0).nullable(),
  width: z.number().int().min(0).nullable(),
  height: z.number().int().min(0).nullable(),
});

export const segmentSchema = z
  .object({
    id: z.string().min(1).max(128),
    start_frame_index: z.number().int().min(0),
    start_time_s: z.number().min(0),
    end_frame_index: z.number().int().min(0),
    end_time_s: z.number().min(0),
    visible_fields: z.array(z.string().min(1)),
    fields: z.record(z.string().min(1), fieldSchema),
  })
  .superRefine((segment, ctx) => {
    if (segment.end_frame_index < segment.start_frame_index) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "end_frame_index must be greater than or equal to start_frame_index",
        path: ["end_frame_index"],
      });
    }
    for (const [name, field] of Object.entries(segment.fields)) {
      if (!segment.visible_fields.includes(name)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `${name} must be visible when enabled`,
          path: ["visible_fields"],
        });
      }
      if (!(name in CANONICAL_FIELD_DEFINITIONS)) {
        if (field.kind === "custom" && name.startsWith("custom_")) {
          continue;
        }
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Unsupported canonical field ${name}`,
          path: ["fields", name],
        });
        continue;
      }
      const expected = CANONICAL_FIELD_DEFINITIONS[name as CanonicalFieldName];
      if (field.kind !== expected.kind || field.stage !== expected.stage) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `${name} must use its canonical type and stage`,
          path: ["fields", name],
        });
      }
    }
  });

const hardcodedStageSchema = z.object({
  velocity_mps: z.number().nullable(),
  altitude_m: z.number().nullable(),
});

export const hardcodedRawPointSchema = z
  .object({
    mission_elapsed_time_s: z.number(),
    stage1: hardcodedStageSchema,
    stage2: hardcodedStageSchema,
    custom_values: z.record(z.string(), z.number()),
  })
  .superRefine((value, ctx) => {
    const present = [
      value.stage1.velocity_mps,
      value.stage1.altitude_m,
      value.stage2.velocity_mps,
      value.stage2.altitude_m,
      ...Object.values(value.custom_values),
    ].some((v) => v !== null && Number.isFinite(v));
    if (!present) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Provide at least one telemetry value",
        path: ["stage1"],
      });
    }
  });

export const unitAliasSchema = z.object({
  aliases: z
    .array(z.string().min(1))
    .min(1, { message: "At least one alias is required" }),
  unit: z.string().min(1),
});

export const fieldKindParsingSchema = z
  .object({
    units: z.record(z.string().min(1), unitAliasSchema).refine((v) => Object.keys(v).length > 0, {
      message: "At least one unit is required",
    }),
    default_unit: z.string().min(1),
    ambiguous_default_unit: z.string().nullable(),
    inferred_units_with_separator: z.array(z.string()),
    inferred_units_without_separator: z.array(z.string()),
    output_unit: z.string().nullable(),
  })
  .superRefine((value, ctx) => {
    const names = new Set(Object.keys(value.units).map((n) => n.toUpperCase()));
    if (!names.has(value.default_unit.toUpperCase())) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["default_unit"],
        message: "default_unit must match a declared unit",
      });
    }
    if (
      value.ambiguous_default_unit &&
      !names.has(value.ambiguous_default_unit.toUpperCase())
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["ambiguous_default_unit"],
        message: "Must match a declared unit",
      });
    }
    for (const inferred of [
      ...value.inferred_units_with_separator,
      ...value.inferred_units_without_separator,
    ]) {
      if (inferred && !names.has(inferred.toUpperCase())) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["inferred_units_with_separator"],
          message: `Inferred unit ${inferred} not in units`,
        });
      }
    }
  });

export const metParsingSchema = z.object({
  timestamp_patterns: z
    .array(z.string().min(1))
    .min(1, { message: "At least one regex pattern is required" })
    .superRefine((patterns, ctx) => {
      patterns.forEach((pat, i) => {
        try {
          new RegExp(pat);
        } catch (err) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: [i],
            message: `Invalid regex: ${(err as Error).message}`,
          });
        }
      });
    }),
});

export const parsingSchema = z.object({
  velocity: fieldKindParsingSchema,
  altitude: fieldKindParsingSchema,
  met: metParsingSchema,
  custom_words: z.array(z.string()),
});

export const quantitySchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1).max(128),
  slug: z.string().min(1),
  dimensionality: z.string().min(1),
  display_unit: z.string().min(1),
  description: z.string(),
  unit_aliases: z.record(z.string(), z.string()),
});

export const profileSchema = z
  .object({
    profile_name: z
      .string()
      .min(1)
      .max(128)
      .refine((v) => IDENTIFIER.test(v), {
        message: "Letters, digits, dot, underscore, dash, space only",
      }),
    description: z.string(),
    default_sample_fps: z.number().positive().max(240),
    default_ocr_workers: z.number().int().min(0),
    ocr_backend: z.enum(["auto", "rapidocr", "vision"]),
    ocr_recognition_level: z.enum(["accurate", "fast"]),
    skip_full_frame_ocr_fallback: z.boolean(),
    fixture_frame_count: z.number().int().min(1).max(2000),
    fixture_time_range_s: z
      .tuple([z.number().min(0), z.number().min(0)])
      .nullable()
      .superRefine((value, ctx) => {
        if (value && value[1] <= value[0]) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: "End must be greater than start",
            path: [1],
          });
        }
      }),
    calibration_video: calibrationVideoSchema,
    video_overlay: videoOverlaySchema,
    trajectory: trajectorySchema,
    parsing: parsingSchema.nullable(),
    custom_telemetry_quantities: z.array(quantitySchema),
    hardcoded_raw_data_points: z.array(hardcodedRawPointSchema),
    segments: z.array(segmentSchema).min(1),
  })
  .superRefine((profile, ctx) => {
    let previousEnd: number | null = null;
    profile.segments.forEach((segment, index) => {
      if (previousEnd !== null && segment.start_frame_index < previousEnd) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "segments must be sorted and non-overlapping",
          path: ["segments", index, "start_frame_index"],
        });
      }
      previousEnd = segment.end_frame_index;
    });
    const quantityById = new Map<string, QuantityValue>();
    const quantityNames = new Set<string>();
    const quantitySlugs = new Set<string>();
    profile.custom_telemetry_quantities.forEach((quantity, index) => {
      if (quantityById.has(quantity.id)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Duplicate custom quantity id ${quantity.id}`,
          path: ["custom_telemetry_quantities", index, "id"],
        });
      }
      const normalizedName = quantity.name.toLowerCase();
      if (quantityNames.has(normalizedName)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Duplicate custom quantity name ${quantity.name}`,
          path: ["custom_telemetry_quantities", index, "name"],
        });
      }
      if (quantitySlugs.has(quantity.slug)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Duplicate custom quantity slug ${quantity.slug}`,
          path: ["custom_telemetry_quantities", index, "slug"],
        });
      }
      quantityById.set(quantity.id, quantity);
      quantityNames.add(normalizedName);
      quantitySlugs.add(quantity.slug);
    });
    const enabledCustomFields = new Set<string>();
    profile.segments.forEach((segment, segmentIndex) => {
      Object.entries(segment.fields).forEach(([fieldName, field]) => {
        if (field.kind !== "custom") {
          return;
        }
        const quantity = field.quantity_id ? quantityById.get(field.quantity_id) : null;
        if (!quantity) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `${fieldName} must reference an embedded custom quantity`,
            path: ["segments", segmentIndex, "fields", fieldName, "quantity_id"],
          });
          return;
        }
        const expectedFieldName = `custom_${quantity.slug}`;
        if (fieldName !== expectedFieldName) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Custom field must be named ${expectedFieldName}`,
            path: ["segments", segmentIndex, "fields", fieldName],
          });
        }
        enabledCustomFields.add(expectedFieldName);
      });
      segment.visible_fields.forEach((fieldName, fieldIndex) => {
        if (fieldName in CANONICAL_FIELD_DEFINITIONS) return;
        if (!fieldName.startsWith("custom_")) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `${fieldName} is not a supported visible field`,
            path: ["segments", segmentIndex, "visible_fields", fieldIndex],
          });
          return;
        }
        const quantity = profile.custom_telemetry_quantities.find(
          (item) => `custom_${item.slug}` === fieldName,
        );
        if (!quantity) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `${fieldName} must reference an embedded custom quantity`,
            path: ["segments", segmentIndex, "visible_fields", fieldIndex],
          });
        }
      });
    });
    profile.hardcoded_raw_data_points.forEach((point, pointIndex) => {
      Object.keys(point.custom_values).forEach((fieldName) => {
        if (!enabledCustomFields.has(fieldName)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `${fieldName} must be enabled in at least one segment before it can have anchor points`,
            path: ["hardcoded_raw_data_points", pointIndex, "custom_values", fieldName],
          });
        }
      });
    });
  });

export const runnableProfileSchema = profileSchema.superRefine((profile, ctx) => {
  let previousEnd: number | null = null;
  profile.segments.forEach((segment, index) => {
    if (segment.end_frame_index <= segment.start_frame_index) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "End frame must be greater than start frame",
        path: ["segments", index, "end_frame_index"],
      });
    }
    if (previousEnd !== null && segment.start_frame_index !== previousEnd) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Segments must be contiguous",
        path: ["segments", index, "start_frame_index"],
      });
    }
    previousEnd = segment.end_frame_index;
    if (!segment.fields.met) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Time field is required",
        path: ["segments", index, "fields", "met"],
      });
    }
    for (const name of CANONICAL_FIELD_ORDER) {
      const field = segment.fields[name];
      if (field && field.bbox_x1y1x2y2 === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Draw a bbox before running",
          path: ["segments", index, "fields", name, "bbox_x1y1x2y2"],
        });
      }
    }
    for (const [name, field] of Object.entries(segment.fields)) {
      if (field.kind === "custom" && field.bbox_x1y1x2y2 === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Draw a bbox before running",
          path: ["segments", index, "fields", name, "bbox_x1y1x2y2"],
        });
      }
    }
  });
  const frameCount = profile.calibration_video.frame_count;
  if (frameCount !== null && profile.segments.length > 0) {
    const last = profile.segments[profile.segments.length - 1];
    if (last.end_frame_index > frameCount) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "End frame exceeds calibration video frame count",
        path: ["segments", profile.segments.length - 1, "end_frame_index"],
      });
    }
  }
});

export type Profile = z.infer<typeof profileSchema>;
export type FieldValue = z.infer<typeof fieldSchema>;
export type SegmentValue = z.infer<typeof segmentSchema>;
export type HardcodedRawPoint = z.infer<typeof hardcodedRawPointSchema>;
export type ParsingValue = z.infer<typeof parsingSchema>;
export type QuantityValue = z.infer<typeof quantitySchema>;

export function canonicalFieldValue(name: CanonicalFieldName): FieldValue {
  const def = CANONICAL_FIELD_DEFINITIONS[name];
  return { kind: def.kind, stage: def.stage, quantity_id: null, bbox_x1y1x2y2: null };
}

export function customFieldValue(quantity: QuantityValue): FieldValue {
  return {
    kind: "custom",
    stage: null,
    quantity_id: quantity.id,
    bbox_x1y1x2y2: null,
  };
}

export function defaultSegmentFields(): Record<string, FieldValue> {
  return Object.fromEntries(
    CANONICAL_FIELD_ORDER.map((name) => [name, canonicalFieldValue(name)]),
  );
}

export function emptyProfile(): Profile {
  return {
    profile_name: "new_profile",
    description: "",
    default_sample_fps: 3.0,
    default_ocr_workers: 0,
    ocr_backend: "auto",
    ocr_recognition_level: "accurate",
    skip_full_frame_ocr_fallback: false,
    fixture_frame_count: 20,
    fixture_time_range_s: null,
    calibration_video: {
      path: null,
      fps: null,
      frame_count: null,
      width: null,
      height: null,
    },
    video_overlay: {
      enabled: true,
      plot_mode: "filtered",
      engine: "auto",
      encoder: "auto",
      width_fraction: 0.5,
      height_fraction: 0.55,
      output_filename: "telemetry_overlay.mp4",
      include_audio: true,
    },
    trajectory: {
      enabled: true,
      interpolation_method: "pchip",
      integration_method: "rk4",
      outlier_rejection_enabled: true,
      outlier_rejection_chi2_threshold: 9,
      outlier_rejection_window_s: 40,
      outlier_preconditioning_enabled: true,
      coarse_step_smoothing_enabled: true,
      coarse_step_max_gap_s: 10,
      coarse_altitude_threshold_m: 500,
      coarse_velocity_threshold_mps: 50,
      acceleration_source_gap_threshold_s: 10,
      derivative_smoothing_window_s: 20,
      derivative_smoothing_polyorder: 3,
      derivative_min_window_samples: 5,
      derivative_smoothing_mode: "interp",
      launch_site: { latitude_deg: null, longitude_deg: null, azimuth_deg: null },
    },
    parsing: null,
    custom_telemetry_quantities: [],
    hardcoded_raw_data_points: [],
    segments: [
      {
        id: "segment_1",
        start_frame_index: 0,
        start_time_s: 0,
        end_frame_index: 1,
        end_time_s: 0,
        visible_fields: [...CANONICAL_FIELD_ORDER],
        fields: defaultSegmentFields(),
      },
    ],
  };
}
