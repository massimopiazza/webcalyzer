# Webcalyzer Internal Guide

This guide documents the internal structure of webcalyzer for developers changing the extraction pipeline, configuration model, CLI, or local web UI. It focuses on ownership boundaries, invariants, and verification checks.

Note: The YAML profile shape is the cross-surface contract. If a configuration field changes, update the dataclasses, YAML I/O, Pydantic models, TypeScript DTOs, Zod schema, and form controls in the same change.

## Contents

| Guide | What it covers |
|---|---|
| [Architecture](architecture.md) | Stack, module responsibilities, runtime flows, and local-app boundaries |
| [Configuration Model](config-model.md) | Four-layer profile contract, validation, conversion, defaults, and compatibility aliases |
| [Pipeline](pipeline.md) | Sampling, OCR, parsing, cleaning, trajectory reconstruction, plotting, and overlay rendering |
| [Web Backend](web-backend.md) | FastAPI endpoints, path safety, template CRUD, jobs, SSE, and static serving |
| [Web Frontend](web-frontend.md) | Routes, API wrapper, form state, docs reader, run console, and UI conventions |
| [File Map](file-map.md) | Annotated repository file map |
| [Function Index](function-index.md) | Key functions, classes, and frontend exports by behavior area |

## Core concepts

**ProfileConfig.** Canonical Python dataclass representation of a run profile. Pipeline code reads this structure directly.

**ProfileModel.** Pydantic v2 validation mirror used by the web backend. API write and run endpoints validate posted JSON through this model.

**Profile DTO.** TypeScript mirror of `ProfileModel` used by the web frontend. Zod performs inline validation before the server validates again.

**Run job.** In-memory background execution record created by `JobManager`. One job may be active at a time.

**OCR Phase A.** Stateless frame work that can run in worker processes. It decodes frames and performs OCR candidate extraction.

**OCR Phase B.** Sequential pass over frame results. It tracks mission elapsed time, stage state, plausibility, and best-measurement selection.

**Resolved profile.** `config_resolved.yaml` written into an output directory so downstream subcommands can reproduce the profile used by the run.

## Non-negotiable invariants

- CLI and web runs must construct equivalent `ProfileConfig` objects for the same YAML shape
- every user-settable profile field must exist in L1, L2, L3, L4, and the TypeScript DTO
- server path handling must keep reads and writes inside configured roots
- heavy optional dependencies should not be imported by the web package at module import time when avoidable
- output directories must contain enough metadata and a resolved profile to reproduce downstream stages
- documentation and UI copy must not use em dashes
