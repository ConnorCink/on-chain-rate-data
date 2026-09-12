
function pct(x) {
  if (x == null || Number.isNaN(Number(x))) return "—";
  return (Number(x) * 100).toFixed(2) + "%";
}

function fmtBlock(n) {
  return n == null ? "—" : Number(n).toLocaleString("en-US");
}

function extractRate(result) {
  const sc = result?.structuredContent || result?.structured_content;
  if (sc && (sc.supply_apr != null || sc.supply_apy != null)) return sc;
  // Some hosts nest under result
  if (result?.result) return extractRate(result.result);
  return null;
}

function extractHistory(result) {
  const sc = result?.structuredContent || result?.structured_content;
  if (sc && Array.isArray(sc.points)) return sc;
  return null;
}

function drawChart(canvas, points) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 360;
  const cssH = canvas.clientHeight || 160;
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const style = getComputedStyle(document.documentElement);
  const ink = style.getPropertyValue("--color-text-primary").trim() || "#1f2937";
  const muted = style.getPropertyValue("--color-text-secondary").trim() || "rgba(127,127,127,0.85)";
  const accent = style.getPropertyValue("--color-accent").trim() || "#1f6b4a";
  const border = style.getPropertyValue("--color-border-primary").trim() || "rgba(127,127,127,0.35)";

  const pad = { t: 12, r: 10, b: 22, l: 42 };
  const w = cssW - pad.l - pad.r;
  const h = cssH - pad.t - pad.b;

  ctx.strokeStyle = border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + h);
  ctx.lineTo(pad.l + w, pad.t + h);
  ctx.stroke();

  if (!points || points.length < 2) {
    ctx.fillStyle = muted;
    ctx.font = "12px var(--font-sans, system-ui)";
    ctx.fillText("No history yet", pad.l + 8, pad.t + h / 2);
    return;
  }

  const aprs = points.map((p) => Number(p.supply_apr));
  let min = Math.min(...aprs);
  let max = Math.max(...aprs);
  if (min === max) {
    min *= 0.98;
    max *= 1.02;
  }
  const span = max - min || 1;

  function xAt(i) {
    return pad.l + (w * i) / (points.length - 1);
  }
  function yAt(v) {
    return pad.t + h - ((v - min) / span) * h;
  }

  // fill
  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + h);
  grad.addColorStop(0, accent + "55");
  grad.addColorStop(1, accent + "00");
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = xAt(i);
    const y = yAt(Number(p.supply_apr));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(xAt(points.length - 1), pad.t + h);
  ctx.lineTo(xAt(0), pad.t + h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // line
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = xAt(i);
    const y = yAt(Number(p.supply_apr));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = accent;
  ctx.lineWidth = 2;
  ctx.stroke();

  // y labels
  ctx.fillStyle = muted;
  ctx.font = "10px var(--font-mono, ui-monospace, monospace)";
  ctx.textAlign = "right";
  ctx.fillText((max * 100).toFixed(2) + "%", pad.l - 6, pad.t + 8);
  ctx.fillText((min * 100).toFixed(2) + "%", pad.l - 6, pad.t + h);
}

export function bootApp({ App, applyDocumentTheme, applyHostStyleVariables, applyHostFonts }) {
  const els = {
    apr: document.getElementById("apr"),
    apy: document.getElementById("apy"),
    block: document.getElementById("block"),
    time: document.getElementById("time"),
    status: document.getElementById("status"),
    canvas: document.getElementById("chart"),
    presets: document.getElementById("presets"),
    refresh: document.getElementById("refresh"),
    root: document.getElementById("app"),
  };

  let activeWindow = "7d";
  let latestRate = null;
  let lastPoints = null;

  const WINDOWS = {
    "24h": { ms: 24 * 3600 * 1000, points: 24 },
    "7d": { ms: 7 * 24 * 3600 * 1000, points: 28 },
    "30d": { ms: 30 * 24 * 3600 * 1000, points: 30 },
    "90d": { ms: 90 * 24 * 3600 * 1000, points: 36 },
  };

  function setStatus(msg) {
    if (els.status) els.status.textContent = msg || "";
  }

  function applyRate(data) {
    if (!data) return;
    latestRate = data;
    els.apy.textContent = pct(data.supply_apy);
    els.apr.textContent = pct(data.supply_apr);
    els.block.textContent = fmtBlock(data.block_number);
    els.time.textContent =
      data.block_timestamp_iso ||
      (data.block_timestamp != null
        ? new Date(Number(data.block_timestamp) * 1000).toISOString().replace(".000", "")
        : "—");
  }

  function isoNow() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  function windowBounds(key) {
    const w = WINDOWS[key] || WINDOWS["7d"];
    const end = Date.now();
    const start = end - w.ms;
    return {
      start_iso: new Date(start).toISOString().replace(/\.\d{3}Z$/, "Z"),
      end_iso: new Date(end).toISOString().replace(/\.\d{3}Z$/, "Z"),
      points: w.points,
    };
  }

  async function loadHistory(key) {
    activeWindow = key;
    [...els.presets.querySelectorAll("button[data-window]")].forEach((b) => {
      b.setAttribute("aria-pressed", b.dataset.window === key ? "true" : "false");
    });
    setStatus("Loading " + key + "…");
    const args = windowBounds(key);
    try {
      const result = await app.callServerTool({
        name: "get_rate_history",
        arguments: args,
      });
      const hist = extractHistory(result);
      if (!hist) throw new Error("No history payload");
      lastPoints = hist.points;
      drawChart(els.canvas, hist.points);
      setStatus(
        key +
          " · " +
          hist.points.length +
          " pts" +
          (hist.cache_hit ? " · cache" : "")
      );
      try {
        await app.updateModelContext?.({
          content: [
            {
              type: "text",
              text:
                "User is viewing Aave V3 ETH USDC supply APR chart window " +
                key +
                " (" +
                args.start_iso +
                " → " +
                args.end_iso +
                ").",
            },
          ],
        });
      } catch (_) {
        /* optional */
      }
    } catch (e) {
      console.error(e);
      setStatus("History failed");
      app.sendLog?.({ level: "error", data: String(e) });
    }
  }

  async function refreshLatest() {
    setStatus("Refreshing…");
    try {
      const result = await app.callServerTool({
        name: "get_aave_usdc_supply_rate",
        arguments: { datetime_iso: isoNow() },
      });
      const rate = extractRate(result);
      if (rate) applyRate(rate);
      await loadHistory(activeWindow);
    } catch (e) {
      console.error(e);
      setStatus("Refresh failed");
      app.sendLog?.({ level: "error", data: String(e) });
    }
  }

  function handleHostContextChanged(ctx) {
    if (!ctx) return;
    if (ctx.theme) applyDocumentTheme(ctx.theme);
    if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
    if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
    if (ctx.safeAreaInsets && els.root) {
      const s = ctx.safeAreaInsets;
      els.root.style.paddingTop = `${s.top || 0}px`;
      els.root.style.paddingRight = `${s.right || 0}px`;
      els.root.style.paddingBottom = `${s.bottom || 0}px`;
      els.root.style.paddingLeft = `${s.left || 0}px`;
    }
    if (lastPoints) drawChart(els.canvas, lastPoints);
  }

  const app = new App(
    { name: "aave-usdc-yield", version: "0.2.0" },
    {},
    { autoResize: true }
  );

  // Register ALL handlers BEFORE connect
  app.onteardown = async () => ({});
  app.ontoolinput = () => {};
  app.ontoolresult = (result) => {
    const rate = extractRate(result);
    if (rate) {
      applyRate(rate);
      // Default chart: 7d via app-only tool (zero model tokens)
      loadHistory(activeWindow || "7d");
    }
  };
  app.onhostcontextchanged = handleHostContextChanged;
  app.onerror = (err) => {
    console.error(err);
    setStatus("App error");
  };

  els.presets.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-window]");
    if (!btn) return;
    loadHistory(btn.dataset.window);
  });
  els.refresh.addEventListener("click", () => refreshLatest());

  app.connect().then(() => {
    handleHostContextChanged(app.getHostContext?.() || null);
    setStatus("Ready");
  });
}
