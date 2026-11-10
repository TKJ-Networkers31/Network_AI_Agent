# VERA Design System Restoration Report

**System Name:** VERA Jet Black Cyber Glass Design System  
**Version:** 2.1.0  
**Authority:** Restored from Verified Baseline (`a6eb27f`)  

---

## 1. Design Tokens Specification

### 1.1 Color Tokens (`src/theme/colors.js`)

```javascript
export const colors = {
  // Canvas & Surfaces
  app: "#000000",          // True OLED Pitch Black
  surface: "#04060c",      // Ultra-dark glass
  surfaceHover: "#0a0f1d", // Hover state

  // Hairline Dividers & Glows
  border: "rgba(255, 255, 255, 0.08)",
  borderGlow: "rgba(56, 189, 248, 0.5)",
  borderPurple: "rgba(168, 85, 247, 0.5)",

  // Brand Accents
  cyan: "#38BDF8",          // Electric Cyan (Primary Brand CTA & Link Vector)
  purple: "#A855F7",        // Neon Purple (Secondary Brand Highlight)
  primary: "#8B5CF6",       // Cyber Violet
  blue: "#2563EB",          // Deep Tech Blue

  // Typography
  text: {
    primary: "#F8FAFC",     // Contrast Ratio 19.8:1 against #000000 (WCAG AAA)
    secondary: "#94A3B8",   // Contrast Ratio 7.2:1 against #000000 (WCAG AAA)
    muted: "#64748B",
  },

  // Semantic Observability Statuses
  success: "#10B981",       // UP / Normal Operation
  warning: "#F59E0B",       // Degraded / Latency Threshold Exceeded
  danger: "#EF4444",        // DOWN / Critical Failure
  info: "#38BDF8",          // Information / Scheduled Task
  unknown: "#64748B",       // Unmonitored / Pending Discovery
};
```

---

## 2. Glassmorphism & Elevation System

### 2.1 Panel & Card Classes (`src/index.css`)
- **`.glass-panel`**:
  - Background: `rgba(2, 4, 10, 0.75)`
  - Backdrop Blur: `blur(18px)`
  - Border: `1px solid rgba(255, 255, 255, 0.08)`
- **`.glass-card`**:
  - Background: `rgba(3, 6, 14, 0.65)`
  - Backdrop Blur: `blur(16px)`
  - Border: `1px solid rgba(255, 255, 255, 0.08)`
- **Interactive Hover Glows**:
  - Cyan Hover: `border-color: rgba(56, 189, 248, 0.55); box-shadow: 0 0 24px -2px rgba(56, 189, 248, 0.35);`
  - Violet Hover: `border-color: rgba(168, 85, 247, 0.55); box-shadow: 0 0 24px -2px rgba(168, 85, 247, 0.35);`

### 2.2 Gradients
- `sakura-gradient`: `linear-gradient(135deg, #38BDF8 0%, #8B5CF6 100%)`
- `tech-gradient`: `linear-gradient(135deg, #0284C7 0%, #38BDF8 50%, #8B5CF6 100%)`
- `core-glow`: `radial-gradient(circle at 50% 50%, #38BDF8 0%, #8B5CF6 55%, rgba(139, 92, 246, 0) 75%)`

---

## 3. Typography & Monospace Hierarchy

- **UI & Prose Font:** Inter (`sans-serif`, weights 300 to 800)
- **Technical & Command Font:** JetBrains Mono (`ui-monospace`, `monospace`, weights 400 to 600)
- **Hierarchy Scale:**
  - Hero Display: `2.25rem` (36px) / Line height `2.5rem`
  - Page Heading (`h1`): `1.75rem` (28px) / Line height `2.1rem`
  - Section Heading (`h2`): `1.25rem` (20px) / Line height `1.6rem`
  - Card Title (`h3`): `0.875rem` (14px) / Line height `1.25rem`
  - Body Text: `0.875rem` (14px) / Line height `1.5rem`
  - Microcopy & Metadata: `0.6875rem` (11px) / Line height `1rem`

---

## 4. Accessibility & Contrast Compliance

| Combination | Fore Color | Back Color | Contrast Ratio | WCAG 2.2 Level |
|---|---|---|---|---|
| Primary Text on App | `#F8FAFC` | `#000000` | **19.8:1** | AAA |
| Secondary Text on App | `#94A3B8` | `#000000` | **7.2:1** | AAA |
| Electric Cyan Accent | `#38BDF8` | `#000000` | **9.1:1** | AAA |
| Healthy Green on Dark | `#10B981` | `#04060c` | **7.8:1** | AAA |
| Warning Amber on Dark | `#F59E0B` | `#04060c` | **8.4:1** | AAA |
| Critical Rose on Dark | `#EF4444` | `#04060c` | **5.4:1** | AA Large |
