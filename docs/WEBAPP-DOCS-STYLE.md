# Webcalyzer Docs Style Guide

## Purpose

This guide captures the writing style used in the webcalyzer documentation under `docs/`. Use it when writing or updating:

- user-facing feature guides in `docs/user/`
- internal architecture and reference docs in `docs/internal/`
- supplementary technical notes that accompany the app, especially pages documenting OCR parsing, filtering, trajectory reconstruction, plotting, overlays, or mathematical expressions


## Two-tier structure

The `docs/` folder has two distinct audiences:

- **User docs** (`docs/user/`): written for people running webcalyzer through the web UI or CLI. They are pedagogical, task-oriented, and use minimal implementation jargon. Focus on what to click or run, why it matters, and how to verify the result.
- **Internal docs** (`docs/internal/`): written for developers changing webcalyzer. They are precise, reference-style, and use code identifiers freely. Focus on how behavior is organized, where invariants live, and which layers must stay in sync.

Both tiers share the core voice and markup conventions below. Internal docs may use more technical density and may omit the "why you would use this" framing that user docs rely on.

## Core voice

Write like a clear product manual, not a tutorial or a blog post.

The voice is:

- direct and task-oriented
- technically precise without being terse
- lightly formal, with complete sentences and no contractions
- never promotional, rhetorical, or chatty

Optimize for scanability. Readers should be able to navigate to a specific feature and read only what they need.

Do not use em dashes. Do not use an ASCII hyphen as a stand-in for an em dash in prose. ASCII hyphens remain correct for e.g. ranges (`1-4`), negative values (`-90`), hyphenated terms (`stage-1`, `single-shot`), subtraction, etc.

## Page structure

### User docs pages

Every user-facing feature page follows this skeleton unless the feature clearly needs a smaller reference shape:

```markdown
# Feature Name

<Opening definition paragraph>

## <Broad group>
### Anatomy of a <feature>
### Create, configure, or run a <feature>
### Edit or review a <feature>

## <Another broad group>
### <Other action>
### <Supplementary detail>
```

**Opening paragraph.** The first paragraph is always a plain-prose definition. It states what the feature is, why it exists, and how it fits into webcalyzer. No heading above it. No bullet list. Two to four sentences maximum.

For a webcalyzer feature page, the pattern is:

- what the feature is
- why it matters for telemetry extraction or review
- where it sits in the workflow

For example:

```markdown
Review frames are sampled JPEGs written before OCR starts. They show representative video frames from the configured calibration window so you can verify that the field boxes cover the right telemetry overlays. Use them after calibration changes and before trusting a long run.
```

### Internal docs pages

Internal pages do not follow a fixed skeleton. They are reference documents. Open with a brief orientation sentence, then group detailed sections under broad H2 headings before going into tables, code blocks, approved diagrams, or annotated file trees.

Internal pages should answer:

- which module owns the behavior
- which data model or API surface is involved
- which invariants must not be broken
- which tests or smoke checks validate the behavior

Do not use "Anatomy of" sections in internal docs. That pattern belongs to user docs.

## Hierarchy

Avoid long flat pages made of many unrelated H2 headings. Use H2 headings as broad groups and H3 headings for the specific actions, concepts, tables, and diagrams inside that group.

Good patterns:

- `## Run Setup` with `### Load a template`, `### Select input and output paths`, and `### Set run overrides`
- `## Signal Conditioning` with `### Clean raw telemetry`, `### Precondition trajectory inputs`, and `### Interpolate sparse measurements`
- `## Job Execution` with `### Job lifecycle`, `### Event stream`, and `### Logging capture`

Keep the specific H3 wording stable when other pages link to that anchor. If you reorganize a page, preserve existing anchor text where practical and update every cross-link that changes.

## Section headings

Use imperative verb phrases for action headings, usually H3:

- `### Run an extraction`
- `### Save a template`
- `### Rebuild clean telemetry`
- `### Render an overlay video`

Use noun phrases for structural or reference headings, especially H2 group headings:

- `## Output files`
- `## Request flow`
- `## Configuration layers`
- `## Trajectory reconstruction model`

Use `### Anatomy of a profile` when the anatomy section sits inside a broader group such as `## Profile Structure`.

H3 headings follow the same conventions and carry most page-level detail. For example, use `### Load a template`, `### Save a template`, and `### Delete a template` under `## Template Actions`.

## The "Anatomy of a X" pattern

Feature pages that describe an entity with named fields use a `### Anatomy of a <feature>` section inside the first broad group after the opening paragraph. This section uses a two-column Markdown table:

```markdown
## Profile Structure

### Anatomy of a profile

| Field | Description |
|---|---|
| **Profile name** (`profile_name`) | Identifier shown in the UI and stored in run metadata. |
| **Default sample fps** (`default_sample_fps`) | Sampling cadence used by OCR when no run override is set. |
| **Fields** (`fields`) | Named video regions mapped to telemetry measurements. |
```

Rules for this table:

- **Field** column: bold the UI display name; add the YAML key in backticks when it helps users map the UI to the profile file
- **Description** column: one or two sentences maximum
- Include enum values as inline code
- Link to another page where a field has a dedicated explanation
- Do not add a `| Type |` column to user-facing anatomy tables. That belongs in internal data-model docs

## UI and code formatting

- **Bold** for all interactive UI elements: button labels, tabs, panels, menu items, toggle labels, and dialog titles
- `backticks` for identifiers, file paths, enum values, commands, YAML keys, function names, and literal tokens
- Use both together when a UI element has a corresponding technical identifier: **Default sample fps** (`default_sample_fps`)
- User docs should avoid source file references unless the user is explicitly editing files
- Internal docs may use source paths and function names freely

Examples:

- Click **Run pipeline** after selecting **Input video** and **Output directory**.
- Set `video_overlay.plot_mode` to `with_rejected` to include outlier markers.
- The web endpoint writes through `save_template(...)`.

## Cross-links

Cross-links are part of the writing style, not an optional polish pass. A page should help the reader move to the prerequisite, the related concept, the configuration surface, and the verification surface without returning to the index.

Link to other user guide pages liberally. Use the feature name as the link text, not a generic phrase:

- `[templates](templates.md)`, not `[here](templates.md)`
- `[calibration](calibration.md)`, not `[the calibration page](calibration.md)`

Within a page, link to a specific section by anchor when the first mention of a sub-concept is far from its explanation. Prefer precise anchors for recurring concepts:

- `[trajectory reconstruction](trajectory-reconstruction.md#integrate-velocity-into-path-distance)`
- `[outputs and review](outputs-and-review.md#review-trajectory)`
- `[profile configuration](profile-configuration.md#customize-parsing)`

Every substantial user-facing page should include at least two contextual links beyond the index link:

- one link to the upstream setup or configuration page when the page depends on prior work
- one link to the downstream review, output, or verification page when the page produces artifacts
- one link to the conceptual background page when the page uses physics, math, parsing, or trajectory terminology

Avoid orphan concepts. If a page introduces a term that has a canonical explanation elsewhere, link the first meaningful mention. Do not save all links for a final "see also" block unless the page already has contextual links in the prose.

Internal docs link to sibling internal docs the same way:

- `[web-backend.md](web-backend.md)`
- `[config-model.md](config-model.md)`

Internal docs may also link to user docs for conceptual explanations that should not be duplicated in architecture docs, for example `[trajectory reconstruction](../user/trajectory-reconstruction.md)`.

## Instruction style

Task sections give step-by-step instructions using a consistent pattern:

1. Lead with a single-sentence instruction that includes the button, page, or command that starts the action.
2. If fields must be filled in, follow with "Fill in:" and a bullet list.
3. Close with important constraints, side effects, or validation checks.

```markdown
## Run an extraction

Open **Run**, select a profile template, choose an input video, and choose an output directory. Click **Run pipeline** to start the job.

Fill in:

- **Profile template:** YAML profile used to configure fields, parsing, trajectory, and overlay settings
- **Input video:** source webcast video readable by OpenCV or AVFoundation
- **Output directory:** directory where CSVs, plots, review frames, and overlay files are written

Note: The run button stays disabled until the profile is valid and both paths are selected.
```

Field bullet lists use the form `**Field name:** explanation`.

## Practical markers

Use these markers sparingly:

- `Note:` for operational constraints, data-loss warnings, or non-obvious system behavior that the user must not miss
- `Remark:` for conceptual clarifications that are helpful but not essential to the task
- `Rule of thumb:` for best-practice advice or naming conventions
- `For instance,` to introduce a concrete example inline in prose

`Note:` is the most common marker. Keep the text after it brief, usually one or two sentences.

During the next documentation refresh, migrate any legacy shorthand markers to these explicit labels.

## Tables

Use a table when presenting:

- feature anatomy
- enum values and meanings
- output file inventories
- API payload shapes
- schema columns or DTO fields
- structured comparisons of alternatives

Table separator rows use no spaces around the pipes:

```markdown
| Field | Description |
|---|---|
```

Do not use tables for sequential steps or prose explanation. Lists or paragraphs are clearer there.

## Lists

Use bullet lists for:

- the "Fill in:" pattern
- short option inventories where order does not matter
- table-of-contents style index entries
- concise pre-flight or verification checklists

Use numbered lists only when sequence matters.

Terminal punctuation:

- omit it on short fragments
- include it when the bullet contains a full sentence

Do not nest bullet lists more than one level deep. If hierarchy is needed, split the content into separate sections or tables.

## Index pages

Each documentation tier has an `index.md` page that acts as a table of contents. The index starts with a short overview, then uses a two-column table:

```markdown
| Guide | What it covers |
|---|---|
```

End index pages with a **Core concepts** section that defines the key domain terms in plain prose with bold lead-in terms:

```markdown
**Profile.** A YAML configuration that defines how one video overlay should be sampled, parsed, filtered, and rendered.
```

This format, bold noun followed by a period and a definition sentence, is the standard pattern for glossary-style entries in index pages.

## Internal docs conventions

In addition to the shared rules above, internal docs use:

- **Code blocks for file trees:** annotated with inline comments describing each entry
- **Mermaid diagrams:** fenced `mermaid` blocks for request, data, pipeline, and state flows
- **Schema tables:** `| Field | Type | Notes |` or `| Column | Type | Notes |`
- **Function signature references:** `function_name(arg)` in backtick code, followed by a plain-prose description
- **Invariants:** short lists of rules that must hold across CLI, web backend, frontend, and YAML profiles
- **Verification notes:** exact commands, tests, or smoke checks that cover the behavior

Use source paths only when they help a developer locate the implementation quickly.

## Diagrams

Use Mermaid for diagrams. Write diagrams as fenced `mermaid` code blocks so the source remains reviewable in Markdown and the web documentation reader can render them as SVG.

Choose the diagram type by the concept:

- `flowchart TD` for runtime pipelines, data transformations, and top-to-bottom phase order
- `flowchart LR` for request handoffs, validation chains, and cross-surface flows
- `sequenceDiagram` for ordered interactions between clients, servers, workers, and external tools
- `stateDiagram-v2` for lifecycle states such as queued, running, cancelled, done, and error

Keep Mermaid node text concise. Put ownership and artifact details in node labels when they help, then move longer constraints into prose or tables below the diagram. File trees remain `text` code blocks, not Mermaid diagrams.

Do not use ASCII arrow diagrams or manually aligned monospaced flow charts for request, state, pipeline, or data-flow diagrams.

## Documentation sidebar behavior

The documentation sidebar separates disclosure from navigation. The chevron arrow is an individual button that only expands or collapses that page's section list. The page title is a separate button that only navigates to the page.

Opening one page's section list must not collapse the others. Multiple pages can stay expanded at once, and the active page should stay expanded.

## Mathematical and quantitative documentation

Webcalyzer needs mathematical and trajectory reconstruction where the pipeline applies numeric transformations, especially trajectory reconstruction and adjacent topics. Put the full conceptual and physical explanation in user docs so readers understand what the tool computes and what assumptions it makes. Internal docs should link to that user-facing explanation and focus on module ownership, invariants, data flow, and verification.

Rendered math uses KaTeX in the web documentation reader. Write standard KaTeX-compatible LaTeX inside `$...$` for inline math and `$$...$$` for display math.

Good candidates for mathematical documentation:

- OCR sample cadence and time grids
- unit conversion into SI values
- interpolation methods such as linear, PCHIP, Akima, and cubic interpolation
- numerical integration methods such as Euler, midpoint, trapezoid, RK4, and Simpson-compatible behavior
- acceleration estimation and Savitzky-Golay derivative smoothing
- coarse-step smoothing and outlier rejection
- altitude, downrange, and total-distance reconstruction
- WGS84 launch-site geodesic projection
- overlay synchronization between mission elapsed time and source video time

### Inline vs display LaTeX

- **Inline LaTeX** (`$...$`): use for short symbolic references embedded in prose, such as `$t_i$`, `$v(t)$`, `$h_{\mathrm{stage1}}$`, or `$0.05 \le f \le 1.0$`
- **Display LaTeX** (`$$...$$`): use for central definitions, derivations, update rules, or expressions that readers need to inspect

Every equation must be preceded by at least one sentence of prose that names the quantities involved and states what the equation expresses. Do not drop an equation into a page without context.

Good pattern:

1. prose sentence that defines the quantities
2. display equation
3. short interpretation or practical remark
4. optional caveat or consequence

Example:

```markdown
The dense trajectory grid uses mission elapsed time as its independent variable. If samples are spaced by $\Delta t$, the grid point after sample $i$ is:

$$
t_{i+1}=t_i+\Delta t
$$

This keeps trajectory outputs aligned with the OCR cadence used during extraction.
```

### Trajectory notation

Use consistent symbols across the trajectory documentation:

| Symbol | Meaning |
|---|---|
| $t$ | mission elapsed time in seconds |
| $v(t)$ | velocity in meters per second |
| $h(t)$ | altitude in meters |
| $a(t)$ | acceleration in meters per second squared |
| $s(t)$ | total path distance in meters |
| $r(t)$ | downrange distance in meters |
| $\Delta t$ | sample spacing in seconds |
| $\phi,\lambda$ | latitude and longitude |
| $\alpha_{\mathrm{az}}$ | launch azimuth |

Use SI units in formulas unless the section is explicitly about parsing or unit conversion.

### Subscripts and superscripts

Semantic labels use `\mathrm{...}`. Whenever a multi-character subscript or superscript denotes a label, role, mode, dataset, stage, or abbreviation rather than a true mathematical index, typeset it in upright roman.

Examples:

- `$h_{\mathrm{stage1}}$`
- `$v_{\mathrm{stage2}}$`
- `$t_{\mathrm{MET}}$`
- `$a_{\mathrm{smooth}}(t)$`
- `$J_{\mathrm{outlier}}$`

Genuine mathematical indices keep the default italic math style:

- `$t_i$`
- `$v_i$`
- `$a_{ij}^{(k)}$`

Mixed labels use `\mathrm{...}` only for the semantic part:

```latex
v_{\mathrm{stage1},i}
```

### Formula examples for this project

Use formulas to document behavior at the level users need to interpret outputs. Keep derivations short and pair them with practical interpretation. When maintainers need the same concept, link from internal docs to the user-facing trajectory reconstruction page instead of duplicating the derivation.

For unit conversion:

```markdown
Each parsed value is converted into SI units before filtering:

$$
x_{\mathrm{SI}} = x_{\mathrm{raw}} \cdot c_{\mathrm{unit}}
$$

The conversion factor $c_{\mathrm{unit}}$ comes from the selected unit definition.
```

For downrange reconstruction:

```markdown
The horizontal downrange increment removes the altitude component from the total path increment:

$$
\Delta r_i = \sqrt{\max\left(0, \Delta s_i^2-\Delta h_i^2\right)}
$$

This prevents climb from being double-counted as horizontal motion.
```

For derivative smoothing:

```markdown
Savitzky-Golay smoothing estimates acceleration by fitting a local polynomial around each sample:

$$
a_{\mathrm{smooth}}(t_i)=\frac{d}{dt}p_i(t)\bigg|_{t=t_i}
$$

The configured window length and polynomial order control how much local structure is preserved.
```

### What not to do with LaTeX

- Do not introduce symbols before the prose defines what they represent
- Do not stack multiple display equations without prose between them
- Do not use LaTeX for simple UI values or file names
- Do not use `\text{...}` as a substitute for `\mathrm{...}` in semantic subscripts
- Do not let a page become visually dominated by equations when a table or prose explanation is clearer

## Verification sections

When a page explains a workflow that can be checked, include a short verification section. Keep it concrete.

Good verification entries:

- output file names to expect
- UI state that confirms success
- command that should complete
- log line or status badge to look for
- small sanity check on generated values

Avoid vague statements such as "make sure it worked." Say what the reader should see.

## What not to do

- Do not open a section with a rhetorical question
- Do not use em dashes
- Do not use an ASCII hyphen as a substitute for an em dash in prose
- Do not overcorrect hyphen use: keep ranges, negative values, hyphenated terms, and subtraction intact
- Do not nest bullet lists more than one level deep
- Do not add a "Summary" or "Next steps" section at the end of a page
- Do not repeat the page title in the opening sentence
- Do not use `(e.g.,)` or `(i.e.,)` with a comma after the abbreviation. Use `(e.g. ...)` and `(i.e. ...)`
- Do not turn every paragraph into a bullet list
