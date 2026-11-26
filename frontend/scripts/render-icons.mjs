import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const here = dirname(fileURLToPath(import.meta.url));
const pub = resolve(here, "..", "public");

const BACKGROUND = "#090b0e";

function pngBuffer(svg, width) {
  const png = new Resvg(svg, { fitTo: { mode: "width", value: width } }).render();
  return { width: png.width, height: png.height, data: png.asPng() };
}

function render(svg, width, outPath) {
  const png = pngBuffer(svg, width);
  writeFileSync(outPath, png.data);
  console.log(`${outPath}  ${png.width}x${png.height}`);
}

// Packs PNGs into a Vista-style ICO. Browsers and Google still request
// /favicon.ico directly, and the SPA fallback used to answer that with HTML.
function buildIco(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);

  let offset = 6 + images.length * 16;
  const entries = images.map((image) => {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(image.width >= 256 ? 0 : image.width, 0);
    entry.writeUInt8(image.height >= 256 ? 0 : image.height, 1);
    entry.writeUInt8(0, 2);
    entry.writeUInt8(0, 3);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(image.data.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += image.data.length;
    return entry;
  });

  return Buffer.concat([
    header,
    ...entries,
    ...images.map((image) => image.data),
  ]);
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

const faviconPngs = [16, 32, 48].map((size) => {
  const png = pngBuffer(favicon, size);
  const outPath = join(pub, `favicon-${size}.png`);
  writeFileSync(outPath, png.data);
  console.log(`${outPath}  ${png.width}x${png.height}`);
  return png;
});
writeFileSync(join(pub, "favicon.ico"), buildIco(faviconPngs));
console.log(`${join(pub, "favicon.ico")}  ${faviconPngs.length} sizes`);
render(wrapAppleTouch(favicon), 180, join(pub, "apple-touch-icon.png"));
render(wrapSocialLogo(logo), 512, join(pub, "logo-512.png"));
