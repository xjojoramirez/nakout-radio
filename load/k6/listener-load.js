// Nightly load canary: 20 virtual users against a throwaway compose stack.
//
// It is deliberately small and forgiving - it does not hunt for the breaking
// point. It fails when requests start erroring or the p95 gets worse, which is
// what catches slow queries, SQLite lock contention and WebSocket leaks.
//
// Override the targets for a local run:
//   API_URL, WEB_URL, WS_URL

import { check, sleep } from "k6";
import http from "k6/http";
import ws from "k6/ws";

const API = __ENV.API_URL || "http://127.0.0.1:8011";
const WEB = __ENV.WEB_URL || "http://127.0.0.1:8012";
const WS = __ENV.WS_URL || "ws://127.0.0.1:8012/api/ws/listeners";

export const options = {
  scenarios: {
    api: {
      executor: "ramping-vus",
      exec: "api",
      startVUs: 0,
      stages: [
        { duration: "10s", target: 20 },
        { duration: "40s", target: 20 },
        { duration: "10s", target: 0 },
      ],
      gracefulRampDown: "5s",
    },
    listeners: {
      executor: "constant-vus",
      exec: "listeners",
      vus: 5,
      duration: "50s",
      startTime: "5s",
      gracefulStop: "10s",
    },
  },
  thresholds: {
    checks: ["rate>0.99"],
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
    ws_connecting: ["p(95)<2000"],
    ws_msgs_received: ["count>0"],
  },
};

export function api() {
  const health = http.get(`${API}/api/health`);
  check(health, {
    "health returns 200": (r) => r.status === 200,
    "health reports ok": (r) => r.json("status") === "ok",
  });

  const genres = http.get(`${API}/api/genres`);
  check(genres, { "genres returns 200": (r) => r.status === 200 });

  const schedule = http.get(`${API}/api/schedule/today`);
  check(schedule, { "schedule returns 200": (r) => r.status === 200 });

  // Goes through nginx, the same path a browser takes in production.
  const page = http.get(`${WEB}/`);
  check(page, {
    "homepage returns 200": (r) => r.status === 200,
    "homepage has the app root": (r) =>
      typeof r.body === "string" && r.body.includes('<div id="root"></div>'),
  });

  sleep(1);
}

export function listeners() {
  const response = ws.connect(WS, {}, (socket) => {
    socket.on("message", (message) => {
      let payload = null;
      try {
        payload = JSON.parse(message);
      } catch {
        payload = null;
      }
      check(payload, {
        "listener payload carries a count": (p) =>
          p !== null && typeof p.count === "number",
      });
    });

    // Hold the connection open. Closing on the first message turns this into
    // a reconnect loop: the server broadcasts on every join, so each close
    // immediately triggers another connect.
    socket.setTimeout(() => socket.close(), 8_000);
  });

  check(response, {
    "websocket handshake accepted": (r) => r != null && r.status === 101,
  });
}

export function handleSummary(data) {
  const metrics = data.metrics;
  const value = (name, key, fallback = 0) =>
    metrics[name] ? metrics[name].values[key] : fallback;

  const lines = [
    "Nightly load test",
    `  http requests: ${value("http_reqs", "count")}`,
    `  failed:        ${(value("http_req_failed", "rate") * 100).toFixed(2)}%`,
    `  p95 latency:   ${value("http_req_duration", "p(95)").toFixed(0)} ms`,
    `  checks passed: ${(value("checks", "rate") * 100).toFixed(2)}%`,
    `  ws messages:   ${value("ws_msgs_received", "count")}`,
  ];

  return {
    stdout: `${lines.join("\n")}\n`,
    "summary.json": JSON.stringify(data, null, 2),
  };
}
