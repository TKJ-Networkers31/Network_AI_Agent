/**
 * src/platform/adaptive-experience/assets/svgBuilder.js
 *
 * Consolidated SVG Sanitization, ViewBox Normalization & Safe Serialization.
 * Shared by Markdown SvgBlock, VAE SvgBlock, and DIO SvgField.
 */

import DOMPurify from "dompurify";

const DEFAULT_VIEWBOX = "0 0 720 400";
const SVG_START_RE = /^\s*(?:<\?xml[^>]*\?>\s*)?(?:<!--[\s\S]*?-->\s*)*<svg[\s>]/i;
const SVG_END_RE = /<\/svg>\s*$/i;

export function isSvgContent(raw) {
  if (typeof raw !== "string") return false;
  return SVG_START_RE.test(raw) && SVG_END_RE.test(raw);
}

/**
 * Sanitizes, validates, measures real bounding box, and serializes
 * raw SVG code into an isolated data URI.
 *
 * Returns null if the input is not valid SVG.
 */
export function buildSafeSvg(code) {
  if (!code || typeof code !== "string") return null;

  // 1. Sanitize with DOMPurify SVG profile
  const clean = DOMPurify.sanitize(code, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_TAGS: ["style"], // Isolated inside <img> data-URI context
  });

  if (!clean || typeof document === "undefined") {
    return null;
  }

  // 2. Parse into temporary off-screen DOM element
  const host = document.createElement("div");
  host.style.cssText =
    "position:absolute;left:-99999px;top:0;visibility:hidden;pointer-events:none;";
  host.innerHTML = clean;

  const svg = host.querySelector("svg");
  if (!svg) return null;

  // 3. Fallback ViewBox initialization
  if (!svg.getAttribute("viewBox")) {
    const w = parseFloat(svg.getAttribute("width"));
    const h = parseFloat(svg.getAttribute("height"));
    svg.setAttribute("viewBox", w > 0 && h > 0 ? `0 0 ${w} ${h}` : DEFAULT_VIEWBOX);
  }

  let viewBoxParts = svg.getAttribute("viewBox").split(/[\s,]+/).map(Number);

  // 4. Measure real bounding box to prevent clipping
  try {
    document.body.appendChild(host);
    const bbox = svg.getBBox();
    const [vx, vy, vw, vh] = viewBoxParts;
    const pad = 8;

    const minX = Math.min(vx, bbox.x - pad);
    const minY = Math.min(vy, bbox.y - pad);
    const maxX = Math.max(vx + vw, bbox.x + bbox.width + pad);
    const maxY = Math.max(vy + vh, bbox.y + bbox.height + pad);

    if (minX !== vx || minY !== vy || maxX !== vx + vw || maxY !== vy + vh) {
      viewBoxParts = [minX, minY, maxX - minX, maxY - minY];
      svg.setAttribute("viewBox", viewBoxParts.join(" "));
    }
  } catch {
    // getBBox fails on empty/headless context — keep existing viewBox
  } finally {
    if (host.parentNode) host.parentNode.removeChild(host);
  }

  const [, , viewBoxWidth, viewBoxHeight] = viewBoxParts;
  const aspectRatio = viewBoxWidth / (viewBoxHeight || 1);

  // 5. Responsive sizing: remove fixed width/height so CSS controls it
  svg.removeAttribute("width");
  svg.removeAttribute("height");

  const xml = new XMLSerializer().serializeToString(svg);
  const widthCap = aspectRatio > 2 ? 1100 : 880;

  return {
    xml,
    uri: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`,
    maxWidth: Math.min(Math.max(viewBoxWidth || 720, 320), widthCap),
    aspectRatio,
  };
}
