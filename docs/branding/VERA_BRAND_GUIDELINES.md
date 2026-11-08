# VERA Brand System & Design Guidelines

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-08  
**Author:** VERA Design System Group  
**Product:** VERA (Enterprise Network Intelligence Platform)  
**Tagline:** Understand. Monitor. Automate.  

---

## 1. Brand Identity & Positioning

### 1.1 Brand Philosophy
**VERA** is an **Enterprise Network Intelligence Platform** built for network architects, NOC operators, and infrastructure reliability engineers. VERA combines real-time network telemetry, automated L1-L3 topology visualization, AI-assisted root-cause diagnostics, and safe, approval-gated network automation.

VERA is **not** a chatbot, novelty assistant, or toy. Its visual and technical identity projects:
- **Intelligent**: Deep algorithmic correlation, multi-layer topology reasoning, and predictive analytics.
- **Precise**: Exact telemetry units, sub-second status refreshes, and zero fabricated topology edges.
- **Reliable**: Mission-critical resilience, read-only boundary enforcement, and predictable operation.
- **Futuristic & Enterprise-Oriented**: Sleek high-density dark interface designed for 24/7 mission control rooms.

> **Note on Name Expansion:** Any speculative expansions such as *"Virtual Enterprise Routing & Analytics"* remain informal proposals and must NOT be used in official brand marks or product documentation. The canonical name is **VERA**.

---

## 2. Visual Identity & Design Tokens

### 2.1 Core Color Palette
All color combinations have been verified against **WCAG 2.2 AA / AAA** contrast criteria:

| Token Name | CSS Variable | Hex Code | Purpose & Application |
|---|---|---|---|
| **Deep Navy** | `--vera-navy-dark` | `#071426` | Primary canvas & app background |
| **Navy Surface** | `--vera-navy-surface` | `#0D2340` | Elevated surfaces (cards, panels, modals, drawers) |
| **Navy Subtle** | `--vera-navy-subtle` | `#122C4F` | Hover highlights, active tab fills, striped table rows |
| **Navy Border** | `--vera-navy-border` | `#1C3B66` | 1px hairline card borders, structural dividers |
| **Electric Blue** | `--vera-blue-electric` | `#176BFF` | Core brand color, primary CTAs, active focus states |
| **Cyan Accent** | `--vera-cyan-accent` | `#54D6FF` | Intelligence core highlights, interactive paths, glow |
| **Ice White** | `--vera-ice-white` | `#EAF2FF` | High-contrast primary headings, numerical values |
| **Steel Gray** | `--vera-steel-gray` | `#8CA0B8` | Muted labels, secondary descriptions, metadata |

### 2.2 Semantic & Operational Telemetry Colors

| Status | Hex Code | Light Tint (Fill) | Purpose & Operational Meaning |
|---|---|---|---|
| **Healthy** | `#22C55E` | `rgba(34, 197, 94, 0.12)` | Link UP, ping responsive, 0% packet loss, verified RIB |
| **Warning** | `#F59E0B` | `rgba(245, 158, 11, 0.12)` | High CPU/RAM utilization, link flapping, jitter > 25ms |
| **Critical** | `#EF4444` | `rgba(239, 68, 68, 0.12)` | Link DOWN, device unreachable, BGP peer down, auth failure |
| **Information**| `#176BFF` | `rgba(23, 107, 255, 0.12)`| Topology sync ongoing, discovery poller scheduled |
| **Unknown** | `#64748B` | `rgba(100, 116, 139, 0.12)`| Maintenance mode, unmonitored node, pending enrollment |

> **WCAG 1.4.1 Requirement:** Never render a status using color alone. Every status badge or table indicator MUST include an explicit icon (e.g. checkmark, alert triangle, X) and a text label.

### 2.3 Typography

- **UI & Display Typography:** `Inter`, system-ui, -apple-system, sans-serif.
  - Used for headings, body copy, button labels, navigation items, and narrative dialogs.
  - Weights: `400` (Regular), `500` (Medium), `600` (Semi-Bold), `700` (Bold).
- **Technical Monospace Typography:** `JetBrains Mono`, `Fira Code`, `ui-monospace`, monospace.
  - Used for all IP addresses (IPv4 / IPv6), CIDR prefixes, MAC addresses, AS numbers, CLI commands, SNMP OIDs, routing tables, and system logs.
  - Weights: `400` (Regular), `500` (Medium).

### 2.4 Spacing & Elevation Scale

- **Grid Unit Base:** `4px` (0.25rem).
- **Layout Spacing:**
  - `xs`: `4px` (gap-1)
  - `sm`: `8px` (gap-2)
  - `md`: `16px` (gap-4)
  - `lg`: `24px` (gap-6)
  - `xl`: `32px` (gap-8)
- **Border Radius Scale:**
  - Control / Button: `6px` (`rounded-md`)
  - Card / Panel: `10px` (`rounded-lg`)
  - Modal / Large Dialog: `14px` (`rounded-xl`)
  - Status Pill: `9999px` (`rounded-full`)
- **Elevation Shadows:**
  - Card: `0 4px 16px -2px rgba(0, 0, 0, 0.4), 0 0 0 1px #1C3B66`
  - Dropdown / Flyout: `0 8px 24px -4px rgba(0, 0, 0, 0.6), 0 0 0 1px #1C3B66`
  - Intelligence Glow: `0 0 20px -2px rgba(23, 107, 255, 0.35)`

---

## 3. Brand Assets & Logo Architecture

### 3.1 Network Core Geometry
The VERA logo is structured around three core architectural tenets:
1. **Network Topology Graph**: Outer nodes representing network infrastructure points (routers, switches, gateways).
2. **Geometric 'V' Conduction Paths**: Precision vector bus lines converging towards the apex.
3. **Central Intelligence Nexus**: A brilliant Cyan and Electric Blue core representing automated correlation, AI diagnostics, and telemetry synthesis.

### 3.2 Asset Matrix & Manifest

The following standard vector SVG assets are generated and maintained in `public/assets/brand/`:
1. `vera-logo-horizontal.svg`: Primary brand mark with VERA wordmark and "Network Intelligence" badge.
2. `vera-symbol-core.svg`: Pure geometric Network Core symbol for application header, sidebar collapse mode, and system icons.
3. `vera-logo-dark.svg`: Optimized for dark surfaces (`#071426` and `#0D2340`).
4. `vera-logo-light.svg`: High-contrast dark vector paths for light documentation surfaces or export reports.
5. `vera-logo-monochrome.svg`: Single-color vector for single-channel thermal printers, CLI ASCII representations, and high-contrast accessibility.
6. `vera-favicon.svg`: Ultra-crisp 16x16 / 32x32 optimized icon for browser tabs.
7. `vera-app-icon.svg`: High-resolution PWA and mobile icon container.
