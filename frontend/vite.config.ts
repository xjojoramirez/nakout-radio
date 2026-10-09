/// <reference types="vitest" />
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const DESCRIPTION =
  "Nakout Radio is a personal, always-on internet radio station playing a curated mix of genres on a time-of-day schedule.";

function seo(siteUrl: string): Plugin {
  const canonical = `${siteUrl}/`;
  const ogImage = `${siteUrl}/logo-512.png`;

  const robots = [
    "User-agent: *",
    "Allow: /",
    "Disallow: /studio",
    "",
    `Sitemap: ${siteUrl}/sitemap.xml`,
    "",
  ].join("\n");

  const sitemap = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    "  <url>",
    `    <loc>${canonical}</loc>`,
    "    <changefreq>hourly</changefreq>",
    "    <priority>1.0</priority>",
    "  </url>",
    "</urlset>",
    "",
  ].join("\n");

  const structuredData = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "RadioStation",
    name: "Nakout Radio",
    url: canonical,
    logo: ogImage,
    description: DESCRIPTION,
    broadcastDisplayName: "Nakout Radio",
  });

  return {
    name: "seo",
    transformIndexHtml() {
      return [
        {
          tag: "link",
          attrs: { rel: "canonical", href: canonical },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { property: "og:url", content: canonical },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { property: "og:image", content: ogImage },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { name: "twitter:image", content: ogImage },
          injectTo: "head",
        },
        {
          tag: "script",
          attrs: { type: "application/ld+json" },
          children: structuredData,
          injectTo: "head",
        },
      ];
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "robots.txt", source: robots });
      this.emitFile({
        type: "asset",
        fileName: "sitemap.xml",
        source: sitemap,
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const siteUrl = (env.VITE_SITE_URL || "http://localhost").replace(/\/+$/, "");

  return {
    plugins: [react(), seo(siteUrl)],
    server: {
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
          ws: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      globals: true,
    },
  };
});
