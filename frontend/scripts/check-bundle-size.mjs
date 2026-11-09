// Fails the frontend build when the gzipped JS or CSS output grows past its
// budget. Run from `frontend/` after `npm run build`.
//
// Sizes are gzip level 9 in kB (1000 bytes). Vite prints its own compressed
// estimate, which differs slightly; the numbers below are the gate's source
// of truth. Raise a budget in this file when growth is intentional; the
// change then shows up in review.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const DIST = fileURLToPath(new URL("../dist/", import.meta.url));

const BUDGET_KB = {
  ".js": Number(process.env.BUNDLE_JS_BUDGET_KB ?? 95),
  ".css": Number(process.env.BUNDLE_CSS_BUDGET_KB ?? 13),
};

function walk(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) files.push(...walk(full));
    else if (entry.isFile()) files.push(full);
  }
  return files;
}

function kb(bytes) {
  return `${(bytes / 1000).toFixed(1)} kB`;
}

try {
  statSync(DIST);
} catch {
  console.error("dist/ not found - run `npm run build` first.");
  process.exit(1);
}

const totals = new Map();
const assets = [];

for (const file of walk(DIST)) {
  const ext = extname(file);
  if (!(ext in BUDGET_KB)) continue;

  const gzip = gzipSync(readFileSync(file), { level: 9 }).length;
  totals.set(ext, (totals.get(ext) ?? 0) + gzip);
  assets.push({
    name: relative(DIST, file).replaceAll("\\", "/"),
    ext,
    gzip,
  });
}

if (assets.length === 0) {
  console.error("No JS or CSS found in dist/ - did the build output change?");
  process.exit(1);
}

assets.sort((a, b) => b.gzip - a.gzip);

console.log("Bundle budget (gzip, level 9)");
for (const [ext, budget] of Object.entries(BUDGET_KB)) {
  const size = totals.get(ext) ?? 0;
  const percent = budget > 0 ? Math.round((size / (budget * 1000)) * 100) : 0;
  console.log(
    `  ${ext.slice(1).toUpperCase().padEnd(3)} ${kb(size).padStart(10)} / ${kb(budget * 1000).padStart(10)}  (${percent}% of budget)`,
  );
}
console.log("  largest assets:");
for (const asset of assets.slice(0, 5)) {
  console.log(`    ${asset.name}  ${kb(asset.gzip)}`);
}

const exceeded = Object.entries(BUDGET_KB).filter(
  ([ext, budget]) => (totals.get(ext) ?? 0) > budget * 1000,
);

if (exceeded.length > 0) {
  console.error("\nBundle budget exceeded:");
  for (const [ext, budget] of exceeded) {
    const size = totals.get(ext) ?? 0;
    console.error(
      `  ${ext.slice(1).toUpperCase()}: ${kb(size)} > ${kb(budget * 1000)} (+${kb(size - budget * 1000)})`,
    );
  }
  console.error(
    "\nIf the growth is intentional, raise the matching budget in\n" +
      "frontend/scripts/check-bundle-size.mjs and explain why in the PR.",
  );
  process.exit(1);
}

console.log("\nBundle size within budget.");
