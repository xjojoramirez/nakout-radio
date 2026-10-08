import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const here = dirname(fileURLToPath(import.meta.url));
const pub = resolve(here, "..", "public");

function render(svg, width, outPath) {
  const png = new Resvg(svg, { fitTo: { mode: "width", value: width } }).render();
  writeFileSync(outPath, png.asPng());
  console.log(`${outPath}  ${png.width}x${png.height}`);
}

// Composites the favicon mark on a full-bleed wood background for iOS.
// iOS applies its own corner mask, so the background must be full-bleed
// (pre-rounded corners would leave black artifacts after masking).
// Assumes favicon.svg viewBox 0 0 64 64: 64*6=384, centered with 64px margin.
function wrapAppleTouch(faviconSvg) {
  const inner = faviconSvg
    .replace(/^[\s\S]*?<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">` +
    `<rect width="512" height="512" fill="#4a2e1e"/>` +
    `<g transform="translate(64 64) scale(6)">${inner}</g></svg>`
  );
}

const favicon = readFileSync(join(pub, "favicon.svg"), "utf8");
const logo = readFileSync(join(pub, "logo.svg"), "utf8");

for (const size of [16, 32, 48]) {
  render(favicon, size, join(pub, `favicon-${size}.png`));
}
render(wrapAppleTouch(favicon), 180, join(pub, "apple-touch-icon.png"));
render(logo, 512, join(pub, "logo-512.png"));
