const PALS: [string, string, string][] = [
  ["#f2a33a", "#7a2e1d", "#1c110a"],
  ["#e9d8b4", "#2f5d62", "#10242a"],
  ["#ff7a59", "#3b1f5e", "#120a24"],
  ["#ffd166", "#c1440e", "#2a0f08"],
  ["#9bd1c1", "#1d3b53", "#0a1824"],
  ["#f4b6c2", "#5a1f3a", "#1c0a14"],
];

export function cssCover(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  const [main, from, to] = PALS[h % PALS.length];
  const k = h % 5;
  const cx = 60 + k * 18;
  const cy = 150 - k * 14;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${from}"/><stop offset="1" stop-color="${to}"/></linearGradient></defs><rect width="200" height="200" fill="url(#g)"/><circle cx="${cx}" cy="${cy}" r="62" fill="${main}"/><circle cx="${cx}" cy="${cy}" r="62" fill="none" stroke="${to}" stroke-width="3" transform="translate(14 -14)"/><rect y="168" width="200" height="32" fill="${to}" opacity=".55"/></svg>`;
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
}
