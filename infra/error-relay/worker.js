
var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// worker.js
var BRAND_COLORS = {
  "TrustOffice": 65657,
  "TrustOffice App": 65657,
  "WingPoint": 2450411,
  "TrustMinutes": 1013358,
  "TrueJoyBirthing": 15485081,
  "AeriusView": 6514417,
  "StenoDesk": 3359061
};
var SEVERITY_ICONS = {
  "uncaught_exception": "\u{1F525}",
  "unhandledrejection": "\u26A0\uFE0F"
};
var recentErrors = /* @__PURE__ */ new Map();
var DEDUPE_MS = 6e4;
function dedupeKey(report) {
  const msg = (report.message || "").slice(0, 100);
  const url = (report.url || "").slice(0, 100);
  const brand = report.brand || "Unknown";
  return `${brand}:${msg}:${url}`;
}
__name(dedupeKey, "dedupeKey");
function shouldSend(report) {
  const key = dedupeKey(report);
  const now = Date.now();
  const last = recentErrors.get(key);
  if (last && now - last < DEDUPE_MS) return false;
  recentErrors.set(key, now);
  if (recentErrors.size > 200) {
    for (const [k, t] of recentErrors) {
      if (now - t > DEDUPE_MS * 5) recentErrors.delete(k);
    }
  }
  return true;
}
__name(shouldSend, "shouldSend");
function formatReport(report) {
  const brand = report.brand || "Unknown";
  const color = BRAND_COLORS[brand] || 7041664;
  const icon = SEVERITY_ICONS[report.error_type] || "\u2757";
  const type = report.error_type || "error";
  const stack = (report.stack_trace || "").slice(0, 1e3);
  const url = (report.url || "").slice(0, 200);
  const message = (report.message || "unknown error").slice(0, 500);
  const session = report.session_id || "";
  const userAgent = (report.user_agent || "").slice(0, 200);
  const fields = [
    { name: "Brand", value: brand, inline: true },
    { name: "Type", value: `${icon} ${type}`, inline: true },
    { name: "URL", value: url || "\u2014", inline: false },
    { name: "Message", value: `\`\`\`${message}\`\`\``, inline: false }
  ];
  if (stack) {
    fields.push({ name: "Stack", value: `\`\`\`${stack}\`\`\``, inline: false });
  }
  if (session) {
    fields.push({ name: "Session", value: session, inline: true });
  }
  if (userAgent) {
    fields.push({ name: "User Agent", value: userAgent, inline: false });
  }
  return {
    embeds: [{
      title: `${icon} ${brand} \u2014 ${type}`,
      color,
      fields,
      timestamp: (/* @__PURE__ */ new Date()).toISOString(),
      footer: { text: "Kit System Health" }
    }]
  };
}
__name(formatReport, "formatReport");
async function handleReport(request, webhookUrl) {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  let report;
  try {
    report = await request.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }
  if (!report || !report.message) {
    return new Response("Missing required fields", { status: 400 });
  }
  if (!shouldSend(report)) {
    return new Response(JSON.stringify({ ok: true, deduped: true }), {
      headers: { "Content-Type": "application/json" }
    });
  }
  const payload = formatReport(report);
  try {
    const resp = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      const text = await resp.text();
      console.error("Discord webhook failed:", resp.status, text);
      return new Response(JSON.stringify({ ok: false, error: "Discord rejected" }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" }
    });
  } catch (err) {
    console.error("Discord webhook error:", err);
    return new Response(JSON.stringify({ ok: false, error: "fetch failed" }), {
      status: 502,
      headers: { "Content-Type": "application/json" }
    });
  }
}
__name(handleReport, "handleReport");
function serveCaptureJs() {
  const js = `
// Auto-init error capture \u2014 loaded from the relay worker
const RELAY_URL = "https://error-relay.kit.workers.dev/report";
let SESSION_ID = ""; try { SESSION_ID = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2,8); } catch {}
let lastSent = 0; const SEEN = new Map(); const WINDOW_MS = 15000; const DEDUPE_MS = 300000;
function send(brand, type, e) {
  const now = Date.now(); if (now - lastSent < WINDOW_MS) return;
  const message = (e && (e.message || e.reason?.message)) || "unknown error";
  const last = SEEN.get(message); if (last && now - last < DEDUPE_MS) return;
  SEEN.set(message, now);
  const stack = e?.stack || e?.reason?.stack || "";
  const url = (typeof window !== "undefined" && window.location?.href) || "";
  let userAgent = ""; try { userAgent = navigator.userAgent || ""; } catch {}
  const body = { brand, session_id: SESSION_ID, error_type: type, message, stack_trace: stack, url, user_agent: userAgent };
  lastSent = now;
  try { fetch(RELAY_URL, { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true, body: JSON.stringify(body) }).catch(() => {}); } catch {}
}
function initErrorCapture(brand) {
  if (typeof window === "undefined" || window.__kitErrorCaptureInstalled) return;
  window.__kitErrorCaptureInstalled = true;
  window.addEventListener("error", (e) => { if (e.message === "Script error.") return; send(brand, "uncaught_exception", e); });
  window.addEventListener("unhandledrejection", (e) => { send(brand, "unhandledrejection", { message: e.reason?.message, reason: e.reason, stack: e.reason?.stack }); });
}
const script = document.currentScript;
if (script && script.dataset.brand) initErrorCapture(script.dataset.brand);
`;
  return new Response(js, {
    headers: {
      "Content-Type": "application/javascript",
      "Cache-Control": "public, max-age=300",
      "Access-Control-Allow-Origin": "*"
    }
  });
}
__name(serveCaptureJs, "serveCaptureJs");
var worker_default = {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type"
        }
      });
    }
    if (url.pathname === "/capture.js") {
      return serveCaptureJs();
    }
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", service: "error-relay" }), {
        headers: { "Content-Type": "application/json" }
      });
    }
    if (url.pathname === "/report") {
      const webhookUrl = env.DISCORD_WEBHOOK_URL;
      if (!webhookUrl) {
        return new Response(JSON.stringify({ ok: false, error: "Webhook not configured" }), {
          status: 500,
          headers: { "Content-Type": "application/json" }
        });
      }
      return handleReport(request, webhookUrl);
    }
    return new Response("Not found", { status: 404 });
  }
};
export {
  worker_default as default
};
//# sourceMappingURL=worker.js.map

