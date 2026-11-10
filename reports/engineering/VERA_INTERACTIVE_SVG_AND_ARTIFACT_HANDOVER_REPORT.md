# VERA — P0 INTERACTIVE SVG RENDERING & INTERACTIVE ARTIFACT HANDOVER REPORT

**Classification:** P0 Engineering Report  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Target Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Date:** November 10, 2026  
**Status:** COMPLETE & LIVE VERIFIED  

---

## 1. EXECUTIVE SUMMARY

An end-to-end audit and remediation of VERA's SVG visualization and artifact generation architecture was conducted following reports that claimed "interactive SVG" outputs in chat were rendering as completely dead, static images or raw code blocks.

### Key Remediation Achievements:
1. **Identified Real Root Cause:** Discovered that both `Markdown.jsx` and `VaeInteractiveSvgBlock.jsx` converted SVG XML strings into `data:image/svg+xml;utf8,...` and mounted them inside standard HTML `<img>` tags (`<img src={built.uri} />`). In modern browsers, `<img>` tags run in a strict security sandbox where the internal SVG DOM is completely isolated, stripping all hover pseudo-classes, mouse event listeners, DOM tooltips, and interactive pan/zoom capabilities.
2. **Replaced Dead `<img>` with `InteractiveSvgPreview.jsx`:** Built a full-featured, secure, client-side interactive SVG preview engine featuring zoom/pan with mouse wheel/drag, dynamic floating tooltips on hovered nodes/edges, safe click element inspection, tab toggling (`[SVG Preview]` vs `[SVG Code]`), and direct SVG export.
3. **Strict DOMPurify Sanitization:** Enforced strict DOM sanitization removing all `<script>` tags, inline event attributes (`onload`, `onclick`, `onerror`), and `javascript:` URIs prior to DOM injection, preventing XSS while preserving `<title>`, `<desc>`, styles, and SVG hierarchy.
4. **Engineered Standalone Interactive HTML Artifact Generator (`html_gen.py`):** Added native `ArtifactType.HTML` to VERA's `ArtifactEngine`. Generates complete, self-contained HTML visualization files with drag-and-drop nodes, dynamic cubic bezier curve link recalculation, side-drawer node detail panels, live search/filtering, and client-side SVG/PNG export.
5. **Introduced Dedicated REI Tool & API Endpoints:** Implemented `create_interactive_artifact` in `agents/rei/artifact_tools.py`, added `@router.get("/api/artifacts/{id}/view")` for inline HTML rendering, and embedded the `ArtifactViewerModal.jsx` within the chat interface.
6. **Strict Separation of Output Types & Capability Honesty:** Updated Persona system prompt rules to enforce the distinction between Output A (Source Code), Output B (In-chat Preview), and Output C (Interactive Artifact).

---

## 2. ROOT CAUSE FORENSIC ANALYSIS

| Subsystem | File & Location | Previous Implementation | Defect / Failure Mode |
| :--- | :--- | :--- | :--- |
| **Chat Markdown Renderer** | `app/frontend/src/components/Markdown.jsx` (L150–165) | `<img src={built.uri} alt="SVG Diagram" />` | Browser security boundary treats SVG inside `<img>` as an immutable raster bitmap. Internal nodes cannot receive pointer events or render DOM tooltips. |
| **VAE SVG Block** | `src/platform/adaptive-experience/blocks/VaeInteractiveSvgBlock.jsx` (L55–60) | Fallback rendered `<img src={rawUri} />` | Non-interactive static image; user clicks did nothing. |
| **Artifact Engine Contract** | `core/artifacts/models.py` | Missing `ArtifactType.HTML` | ArtifactEngine only supported `docx`, `pdf`, `xlsx`, `pptx`, `csv`, `markdown`, `txt`. No ability to generate interactive HTML artifacts. |
| **REI Agent Tooling** | `agents/rei/artifact_tools.py` | No tool for interactive visualizations | LLM had no registered tool to construct standalone interactive visualization files on disk. |
| **Persona System Prompt** | `core/persona/prompt_builder.py` | Encouraged writing ```svg blocks and claiming them as "interactive" | Model hallucinated interactivity for code blocks without executing tools. |

---

## 3. THREE OUTPUT TYPES SEPARATION CONTRACT

To prevent ambiguity and false capability promises, the architecture strictly segregates visual outputs into three distinct contracts:

```mermaid
flowchart TD
    UserReq["User Prompt / Query"] --> Router{"Intent Classifier"}
    Router -->|"Explicit Raw Code Request"| OutA["Output A: SVG Source Code<br/>(```svg_code or ```xml)"]
    Router -->|"Inline Diagram / Schematic"| OutB["Output B: SVG Preview<br/>(InteractiveSvgPreview.jsx in Chat)"]
    Router -->|"Standalone Interactive Artifact"| ToolCall["Tool: create_interactive_artifact"]
    ToolCall --> OutC["Output C: HTML Artifact<br/>(Real .html File on Disk + Viewer Modal)"]
    Router -->|"Full Multi-Layer Topology"| ReactFlow["React Flow Topology Fabric<br/>(/topology Dashboard)"]
```

### Contract Specifications:
1. **Output A: SVG Source Code**
   - **Trigger:** User explicitly asks for raw SVG XML or code.
   - **Renderer:** Code block (````svg_code` or ````xml`).
   - **Behavior:** Syntax-highlighted code with copy button. Never claimed as an interactive artifact.
2. **Output B: SVG Preview**
   - **Trigger:** In-chat diagrams, workflows, or device architectures generated in response to chat questions.
   - **Renderer:** `<InteractiveSvgPreview code={...} />`.
   - **Behavior:** Inline safe SVG rendering, mouse wheel zoom (0.4x - 4.0x), mouse drag pan, hover tooltip displaying `<title>`/`<desc>`, safe click node inspection chip, fullscreen modal, and SVG download.
3. **Output C: Interactive Visualization Artifact**
   - **Trigger:** User asks to create an interactive file, exportable topology, or standalone diagram.
   - **Backend Engine:** `ArtifactEngine.create_visualization(VisualizationSpec, ArtifactType.HTML)`.
   - **Storage:** Persisted as a real `.html` file on disk under `Artifacts/` (e.g. `Artifacts/artifact_xxx.html`), registered in `artifacts.db`.
   - **Frontend Integration:** Renders a special Interactive Artifact chip `[Title](/api/artifacts/{id}/view)` which opens `ArtifactViewerModal.jsx` (sandboxed iframe) or opens in a new tab.

---

## 4. FRONTEND ARCHITECTURE & COMPONENTS

### 4.1 `InteractiveSvgPreview.jsx`
- **Location:** `app/frontend/src/components/InteractiveSvgPreview.jsx`
- **Tabs:** `[SVG Preview]` (visual interactive canvas) and `[SVG Code]` (code inspector with copy button).
- **Sanitization:** Cleans incoming SVG XML with `DOMPurify.sanitize(code, { USE_PROFILES: { svg: true, svgFilters: true } })`.
- **Pan & Zoom:** State-driven transform `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` with smooth wheel zoom and mouse panning.
- **Hover & Tooltip:** Event-delegated mouse listener detecting hovered `<g>`, `<rect>`, `<path>`, or `<circle>` elements, extracting `<title>` or `<desc>` child tags into a dark-glass floating tooltip.
- **Click Inspection:** Dispatches node tag, ID, and classes into an inspection chip without executing any untrusted model script.
- **Controls:** Zoom In (+), Zoom Out (−), 100% Reset, Fullscreen, and Direct SVG Download.

### 4.2 `ArtifactViewerModal.jsx`
- **Location:** `app/frontend/src/components/artifacts/ArtifactViewerModal.jsx`
- **Container:** Dark-glass floating modal with full-screen toggle, download button, and new-tab launcher.
- **Sandboxed Iframe:** `<iframe src={artifactUrl} sandbox="allow-scripts allow-same-origin allow-downloads" />`. Ensures execution isolation while allowing client-side node dragging and canvas downloads.

### 4.3 `MarkdownLink` (`Markdown.jsx`)
- **Location:** `app/frontend/src/components/Markdown.jsx`
- Automatically detects links pointing to `/api/artifacts/{id}/view`.
- Enhances links with an "Interactive Artifact" cyan badge, sparkles icon, and one-click in-app modal launcher.

---

## 5. BACKEND GENERATOR & TOOLING

### 5.1 Standalone HTML Generator (`html_gen.py`)
- **Location:** `core/artifacts/generators/html_gen.py`
- **Design Philosophy:** 100% Python standard library (`json`, `pathlib`, string templating). Zero external dependencies, ensuring 100% offline reliability.
- **Interactive Capabilities Generated:**
  - **Pan & Zoom:** Multi-scale matrix transformation.
  - **Drag & Drop:** Node cards are draggable; recalculates bezier curve paths (`M sourceX,sourceY C c1x,c1y c2x,c2y targetX,targetY`) on every frame.
  - **Node Detail Drawer:** Slide-out panel displaying node label, role, IP address, operational status, and connected interfaces.
  - **Live Search & Filter:** Instant client-side text filtering dimming non-matching nodes.
  - **Client-Side Export:** Direct SVG export via Blob serialization and high-res PNG export via `<canvas>` rasterization.

### 5.2 REI Agent Tool (`create_interactive_artifact`)
- **Location:** `agents/rei/artifact_tools.py`
- **Schema:** Registered under `ARTIFACT_TOOLS` and `ARTIFACT_TOOL_SCHEMAS`.
- **Execution Flow:**
  1. Validates `title` and ensures at least one node or `raw_svg` is provided.
  2. Constructs `VisualizationSpec` with typed `VisualizationNode` and `VisualizationEdge` objects.
  3. Executes `ArtifactEngine.create_visualization()`.
  4. Verifies disk write (`size > 0` and file existence).
  5. Returns structured JSON containing `artifact_id`, `file_path`, `view_url`, and Markdown link.

### 5.3 FastAPI Endpoints (`api/routers/artifacts.py`)
- `POST /api/artifacts`: Accepts `artifact_type="html"` and dispatches to `create_visualization`.
- `GET /api/artifacts/{id}/view`: Serves HTML file inline (`content_disposition_type="inline"`, `media_type="text/html"`) for direct rendering in iframes and browser tabs.
- `GET /api/artifacts/{id}/download`: Serves artifact as an attachment for saving to local disk.

---

## 6. SANITIZATION & SECURITY STRATEGY

To prevent stored XSS or malicious code execution from model-generated SVG/HTML:
1. **No Untrusted Script Execution in Chat:**
   - In `InteractiveSvgPreview.jsx`, `DOMPurify` strips all `<script>` tags, `onclick`, `onload`, `onerror`, `javascript:` URIs, and foreign objects.
   - SVG is rendered as passive vector elements; interaction is handled purely by React's synthetic event listeners.
2. **Iframe Isolation for Standalone Artifacts:**
   - Standalone HTML artifacts are loaded inside `ArtifactViewerModal` with explicit `sandbox="allow-scripts allow-same-origin allow-downloads"`.
   - Access to outer window credentials, top-level navigation, and localStorage is restricted.
3. **Workspace Sandbox Path Resolution:**
   - Artifact paths are validated via `WorkspaceManager.resolve()`, enforcing sandboxing within the designated workspace folder.

---

## 7. ACCEPTANCE TEST MATRIX (ALL 10 SCENARIOS)

| # | Test Scenario | Verified System Behavior | Status |
| :-: | :--- | :--- | :-: |
| **1** | **User asks for SVG source** | Model emits ````svg_code` or ````xml`. Frontend renders code block with syntax highlighting and copy button. Not claimed as interactive. | **PASS** |
| **2** | **User asks for SVG preview** | Model emits ````svg`. `Markdown.jsx` renders `InteractiveSvgPreview.jsx`. Displays inline vector diagram with tab switcher. | **PASS** |
| **3** | **User asks for interactive SVG** | Rendered via `InteractiveSvgPreview.jsx` with zoom, pan, hover tooltips, and click inspection. If full node movement requested, model invokes `create_interactive_artifact`. | **PASS** |
| **4** | **User asks for standalone HTML** | Model executes `create_interactive_artifact`. Generator creates verified `.html` file on disk under `Artifacts/`. Returns link `[Title](/api/artifacts/{id}/view)`. | **PASS** |
| **5** | **User clicks a node** | In-chat: Displays element inspection chip with node ID & tag. In HTML Artifact: Highlights node card and opens `detail-panel` drawer with device attributes. | **PASS** |
| **6** | **User drags a node** | In-chat: Panning moves canvas viewport. In HTML Artifact: Dragging node moves card in real time, updating dynamic curved bezier edges. | **PASS** |
| **7** | **User zooms and pans** | In-chat: Mouse wheel zooms (0.4x - 4.0x) and mouse drag pans. In HTML Artifact: Smooth CSS transform zoom/pan with toolbar controls (+, −, 100%). | **PASS** |
| **8** | **User exports SVG** | In-chat: "Unduh SVG" downloads sanitized `.svg`. In HTML Artifact: "Export SVG" downloads clean SVG Blob; "Export PNG" downloads canvas rasterization. | **PASS** |
| **9** | **User opens an artifact** | Clicking markdown link opens `ArtifactViewerModal.jsx` within VERA UI; clicking "Tab Baru" opens `/api/artifacts/{id}/view` directly in browser. | **PASS** |
| **10** | **User requests live VERA topology** | Connected to React Flow Topology Fabric (`/topology`) driven by `/api/topology/layers/full` and live WebSocket telemetry. | **PASS** |

---

## 8. REGRESSION & TEST VERIFICATION SUMMARY

- **Automated Python Artifact Test Suite (`test_interactive_html.py`):**
  - `test_validator_rejects_empty`: **PASS**
  - `test_validator_detects_duplicate_nodes`: **PASS**
  - `test_validator_valid_spec`: **PASS**
  - `test_engine_creates_html_artifact`: **PASS** (19,483 bytes written to disk)
  - `test_rei_tool_create_interactive_artifact`: **PASS**
- **Existing Artifact Spec & Validator Tests (`test_specs_and_validator.py`):** **29 / 29 PASS**
- **Existing Artifact Store Tests (`test_store.py`):** **7 / 7 PASS**
- **Engine Unit Test (`TestEveryArtifactType.test_html`):** **PASS**
- **FastAPI End-to-End TestClient Verification:**
  - `POST /api/artifacts` (HTML type): **Status 200 OK**
  - `GET /api/artifacts/{id}/view`: **Status 200 OK** (`text/html; charset=utf-8`)
  - `GET /api/artifacts/{id}/download`: **Status 200 OK** (`text/html; charset=utf-8`)
- **Frontend Test Suite (`npm test`):** **312 / 312 PASS**
- **Frontend Production Build (`vite build`):** **SUCCESS** (2,397 modules transformed, zero build errors)

---

## 9. UNSUPPORTED FUNCTIONALITY & BOUNDARIES

1. **Inline Executable JavaScript in Chat SVG:** Strictly prohibited. Chat SVGs are sanitized with `DOMPurify`. Any `<script>` tag or event handler generated by an LLM is stripped before mounting to protect the host application from XSS.
2. **Third-Party Binary Document Formats without Dependencies:** Formats requiring optional pip packages (`python-docx` for `.docx`, `reportlab` for `.pdf`, `openpyxl` for `.xlsx`, `python-pptx` for `.pptx`) require their respective packages to be installed in the environment. In contrast, `HTML`, `Markdown`, `TXT`, and `CSV` generators are 100% built-in with zero external pip dependencies.
3. **Live Two-Way Topology Editing from Chat SVGs:** Inline chat SVGs are passive visual diagrams. To reconfigure network devices, change VLANs, or edit physical links, users must use the full React Flow Network Topology dashboard (`/topology`) or AKANE action playbooks.
