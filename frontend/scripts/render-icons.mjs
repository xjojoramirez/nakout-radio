import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const here = dirname(fileURLToPath(import.meta.url));
const pub = resolve(here, "..", "public");

const BACKGROUND = "#090b0e";

function render(svg, width, outPath) {
  const png = new Resvg(svg, { fitTo: { mode: "width", value: width } }).render();
  writeFileSync(outPath, png.asPng());
  console.log(`${outPath}  ${png.width}x${png.height}`);
}

function inner(svg) {
  return svg
    .replace(/^[\s\S]*?<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "");
}

// Composites the favicon mark on a full-bleed background for iOS.
// iOS applies its own corner mask, so the background must be full-bleed
// (pre-rounded corners would leave black artifacts after masking).
// favicon.svg viewBox 0 0 64 64; its ink spans x 8..56 and y 5..61, so a 7x
// scale centered in 512 needs translate(32 25).
function wrapAppleTouch(faviconSvg) {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">` +
    `<rect width="512" height="512" fill="${BACKGROUND}"/>` +
    `<g transform="translate(32 25) scale(7)">${inner(faviconSvg)}</g></svg>`
  );
}

// The social/JSON-LD logo gets the same full-bleed graphite so its cream
// outline survives light link previews. logo.svg itself stays transparent.
function wrapSocialLogo(logoSvg) {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">` +
    `<rect width="512" height="512" fill="${BACKGROUND}"/>` +
    `${inner(logoSvg)}</svg>`
  );
}

const favicon = readFileSync(join(pub, "favicon.svg"), "utf8");
const logo = readFileSync(join(pub, "logo.svg"), "utf8");

for (const size of [16, 32, 48]) {
  render(favicon, size, join(pub, `favicon-${size}.png`));
}
render(wrapAppleTouch(favicon), 180, join(pub, "apple-touch-icon.png"));
render(wrapSocialLogo(logo), 512, join(pub, "logo-512.png"));
