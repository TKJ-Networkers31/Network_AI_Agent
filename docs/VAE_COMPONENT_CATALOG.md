# VERA Adaptive Experience (VAE) — Component Catalog

**Catalog Version:** 1.0.0  
**Platform:** VERA Presentation Layer  

This catalog details the standard visual and interactive components registered within the VERA Adaptive Experience (VAE) ecosystem.

---

## 1. Registry Index

| Block Type | Component Path | Lazy Loaded | Error Boundary Protected |
|---|---|---|---|
| `markdown` | `src/components/Markdown.jsx` | No | Yes |
| `text` | `src/components/Markdown.jsx` | No | Yes |
| `metric-card` | `src/components/MetricCard.jsx` | No | Yes |
| `dio-interaction` | `src/components/dio/Renderer.jsx` | No | Yes |
| `action-card` | `src/platform/adaptive-experience/interactions/UnifiedActionCard.jsx` | Yes | Yes |
| `unified-action-card` | `src/platform/adaptive-experience/interactions/UnifiedActionCard.jsx` | Yes | Yes |
| `graph` | `src/components/GraphBlock.jsx` | Yes | Yes |
| `map` | `src/components/MapBlock.jsx` | Yes | Yes |
| `mermaid` | `src/components/MermaidBlock.jsx` | Yes | Yes |
| `unknown` | `src/platform/adaptive-experience/renderer/UnknownBlockFallback.jsx` | No | Yes |

---

## 2. Component Specifications

### 2.1 UnifiedActionCard (`UnifiedActionCard.jsx`)

Consolidates remediation scripts, target device identification, semantic risk badges, RBAC pre-flight simulation, and execution approval workflows.

- **Props:**
  - `data`: Structured action definition (`title`, `target_device`, `risk_level`, `syntax`, `description`, `requires_approval`).
  - `code`: Raw JSON string fallback (for compatibility with Markdown code fences).
  - `onActionInvoke`: Callback function invoked upon execution.
- **Visual Design:**
  - Background: Deep Navy (`#071426`).
  - Header: Shield icon with Cyan accent (`#54D6FF`), Electric Blue action accents.
  - Risk Badges:
    - `READ_ONLY`: Blue border & fill.
    - `LOW`: Emerald border & fill.
    - `MEDIUM`: Amber border & fill.
    - `HIGH`: Orange border & fill.
    - `CRITICAL`: Rose border & fill.
- **Interactivity:**
  - One-click syntax copy.
  - "Simulasi Otorisasi": Calls `ActionGateway.simulatePermission` without executing commands.
  - "Setujui Eksekusi" / "Tolak": Human-in-the-loop approval mechanism with feedback.

---

### 2.2 MermaidBlock (`MermaidBlock.jsx`)

A high-performance visual diagram renderer for Mermaid flowcharts and architecture topologies without heavy external bundle overhead.

- **Engine:** `src/platform/adaptive-experience/renderer/mermaidParser.js`
- **Supported Directions:** `TD`, `TB`, `LR`, `RL`, `BT`.
- **Supported Connectors:** Directed arrows (`-->`), dotted (`-.->`), thick (`==>`), line (`---`), labeled edges (`-->|label|`).
- **Features:**
  - Crisp SVG rendering with Electric Blue path strokes and Dark Navy node cards.
  - View Toggle: Easily switch between interactive visual diagram and raw Mermaid syntax.
  - One-click syntax copying.

---

### 2.3 Markdown & StreamingMarkdown

The foundational prose presentation engine.

- **Engine:** ReactMarkdown v9 with remark-gfm, remark-math, and rehype-katex.
- **Features:**
  - Clickable inline code chips with auto-copy.
  - LaTeX mathematical equations.
  - Automatic detection and rendering of fenced code blocks into specialized VAE components (SVG, Mermaid, Graph, Map, Action Cards).
  - Consolidated SVG pipeline: Sandboxed <img> data URIs with auto-scaled bounding boxes.
  - SSRF-protected Markdown images via `imagePolicy.js`.

---

### 2.4 MetricCard (`MetricCard.jsx`)

Compact KPI card for displaying network telemetry indicators (latency, packet loss, BGP flap rate).

- **Props:**
  - `title`: String metric name.
  - `value`: Number or formatted string value.
  - `unit`: Telemetry unit (`ms`, `pps`, `%`).
  - `trend`: Direction (`"up"`, `"down"`, `"neutral"`).
  - `status`: Health status (`"healthy"`, `"warning"`, `"critical"`).

---

### 2.5 UnknownBlockFallback (`UnknownBlockFallback.jsx`)

Graceful degradation component rendered when an unsupported block type is encountered.

- **Features:**
  - Non-intrusive card highlighting the unrecognized type name.
  - Collapsible JSON inspection drawer for developers and administrators.
  - Prevents entire chat bubble crash or blank render.

---

### 2.6 ComponentErrorBoundary (`ComponentErrorBoundary.jsx`)

React error boundary wrapping every rendered block independently.

- **Guarantee:** A runtime render error in a single complex block (e.g., malformed graph or corrupted Leaflet coordinates) will isolate and degrade that single block only, leaving the surrounding conversation and interactive components fully functional.
