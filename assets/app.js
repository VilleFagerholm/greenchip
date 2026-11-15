(() => {
  const banner = document.getElementById("error-container");
  const previewToggle = document.getElementById("previewToggle");
  const previewStateEl = document.getElementById("previewState");
  const previewZoomEl = document.getElementById("previewZoom");
  const videoFeed = document.getElementById("videoFeed");
  const videoPlaceholder = document.getElementById("videoPlaceholder");

  let failCount = 0;
  let previewState = "off";
  let frameTimer = null;
  let objectUrl = null;

  function setBanner(show, text) {
    if (!banner) return;
    banner.style.display = show ? "block" : "none";
    if (text) banner.textContent = text;
  }

  function text(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value == null || value === "" ? "--" : String(value);
  }

  function fmt(v, digits = 1) {
    if (v == null || Number.isNaN(v)) return "--";
    return Number(v).toFixed(digits);
  }

  function presenceLabel(v) {
    if (v === true) return "PRESENT";
    if (v === false) return "ABSENT";
    return "UNKNOWN";
  }

  function renderEnergyHeatmap(hm) {
    const strip = document.getElementById("energyStrip");
    const unavail = document.getElementById("heatmapUnavailable");
    const labelEl = document.getElementById("heatmapLabel");
    if (!strip) return;
    const available = !!(hm && hm.available);
    let bins = available && Array.isArray(hm.bins) ? hm.bins.slice() : [];
    if (labelEl) {
      labelEl.textContent = (hm && hm.label) || "Energy over time";
      if (labelEl.textContent.includes("not a room map")) {
        labelEl.textContent = "Energy over time";
      }
    }
    if (unavail) {
      unavail.hidden = available;
      unavail.textContent = available ? "" : "Acoustic input unavailable / not updating";
    }
    strip.setAttribute("data-unavailable", available ? "0" : "1");
    strip.replaceChildren();
    if (!available) return;
    // Waveform look: keep a glanceable number of bars (newest on the right).
    const maxBars = 40;
    if (bins.length > maxBars) bins = bins.slice(bins.length - maxBars);
    while (bins.length < 24) bins.unshift(0);
    bins.forEach((v, idx) => {
      const cell = document.createElement("span");
      cell.className = "energy-cell";
      let i = Math.max(0, Math.min(1, Number(v) || 0));
      // Soft envelope so a flat quiet room still reads as a gentle wave.
      const wave = 0.12 + 0.1 * Math.sin((idx / bins.length) * Math.PI * 3);
      i = Math.max(0, Math.min(1, i * 0.88 + wave * (0.35 + i * 0.65)));
      cell.style.setProperty("--i", String(i));
      strip.appendChild(cell);
    });
  }

  function renderDetections(list, peopleCount) {
    const cue = document.getElementById("detectCue");
    if (!cue) return;
    const dets = Array.isArray(list) ? list : [];
    const nPeople = peopleCount != null ? Number(peopleCount) : dets.filter((x) => x.label === "person").length;
    if (!dets.length) {
      cue.textContent = "YOLO on-device · no objects";
      return;
    }
    const top = dets.slice(0, 4).map((x) => {
      const c = Number(x.confidence);
      return `${x.label}${Number.isFinite(c) ? ` ${Math.round(c * 100)}%` : ""}`;
    }).join(" · ");
    cue.textContent = `People ${nPeople} · ${top}`;
  }

  function applySnapshot(d) {
    if (d.product_title) text("productTitle", d.product_title);
    text("uptimeMeta", d.uptime_s != null ? `uptime ${Math.round(d.uptime_s)}s` : "uptime --");

    text("tempValue", fmt(d.temperature_c));
    text("humidityValue", fmt(d.humidity_pct, 0));
    text("normalValue", fmt(d.room_normal_c));
    text("dropValue", fmt(d.drop_c));

    const pp = d.people_present;
    text("peoplePresentLabel", presenceLabel(pp).toLowerCase());
    const pBadge = document.getElementById("presenceBadge");
    if (pBadge) {
      pBadge.textContent = presenceLabel(pp);
      pBadge.className = "presence-badge " + (
        pp === true ? "present" : pp === false ? "absent" : "unknown"
      );
    }

    const occ = document.getElementById("occupancyBadge");
    if (occ) {
      occ.textContent = (d.occupancy || "--").toUpperCase();
      occ.className = "status-chip " + (d.occupancy || "");
    }
    const last = d.last_move_s == null
      ? ""
      : `Last move ${Math.round(d.last_move_s)}s · empty after 10 min still`;
    text("occupancyDetail", last);

    const badge = document.getElementById("sentinelBadge");
    if (badge) {
      badge.textContent = d.draft_label || "--";
      badge.className = "status-chip " + (d.alert || "");
    }
    text("sentinelReason", d.draft_reason || "");
    const coldOn = !!(d.signals && d.signals.cold);
    const winOn = !!(d.signals && d.signals.window);
    const noiseOn = !!(d.signals && d.signals.noise);
    const drop = d.drop_c;
    const rise = d.noise && d.noise.rise_db;
    text(
      "sigColdDetail",
      coldOn
        ? (drop != null ? `on · −${fmt(drop)}°C` : "on")
        : (drop != null ? `off · −${fmt(drop)}°C` : "off"),
    );
    text(
      "sigWindowDetail",
      winOn ? "on · changed" : (d.calibration ? "calibrating…" : "off"),
    );
    text(
      "sigNoiseDetail",
      noiseOn
        ? (rise != null ? `on · +${fmt(rise)} dB` : "on")
        : (rise != null ? `off · +${fmt(rise)} dB` : "off"),
    );
    ["sigCold", "sigWindow", "sigNoise"].forEach((id, i) => {
      const on = [coldOn, winOn, noiseOn][i];
      const el = document.getElementById(id);
      if (el) el.classList.toggle("active", on);
    });

    const n = d.noise || {};
    const noiseStatus = document.getElementById("noiseStatus");
    if (noiseStatus) {
      noiseStatus.textContent = n.db == null ? "--" : n.noisy ? "NOISY" : "QUIET";
      noiseStatus.className = "status-chip " + (n.noisy ? "noisy" : "quiet");
    }
    text("noiseDb", fmt(n.db));
    text("noiseMedian", fmt(n.median_db));
    text("noiseRise", fmt(n.rise_db));
    renderEnergyHeatmap(n.heatmap);
    renderDetections(d.detections, d.people_count);

    const snoozeBtn = document.getElementById("snoozeButton");
    if (snoozeBtn) {
      snoozeBtn.disabled = false;
      snoozeBtn.textContent = d.snooze_remaining_s > 0
        ? `Snooze ${d.snooze_remaining_s}s`
        : "Snooze 15 min";
    }

    const matrix = document.getElementById("matrixMirror");
    if (matrix) {
      const bits = [
        (d.draft_label || "IDLE"),
        d.occupancy || "?",
        d.preview === "on" ? "PREVIEW" : "",
        d.snooze_remaining_s > 0 ? `SNOOZE ${d.snooze_remaining_s}s` : "",
      ].filter(Boolean);
      matrix.textContent = bits.join(" · ");
    }
    const buzzer = document.getElementById("buzzerMirror");
    if (buzzer) {
      const a = d.alert || "idle";
      buzzer.textContent = a === "audible" || a === "visual" ? a.toUpperCase() : "STANDBY";
    }

    const parts = d.parts || {};
    const partsList = document.getElementById("partsList");
    if (partsList) {
      partsList.innerHTML = "";
      Object.entries(parts).forEach(([name, state]) => {
        const span = document.createElement("span");
        span.className = "part-chip " + state;
        span.textContent = `${name} ${state}`;
        partsList.appendChild(span);
      });
    }

    const today = d.today || {};
    text("todayEvents", today.events != null ? today.events : 0);
    text("todayMinutes", fmt(today.minutes));
    text("todayDm", fmt(today.degree_minutes));
    const recentEvents = document.getElementById("recentEvents");
    if (recentEvents) {
      recentEvents.innerHTML = "";
      (today.recent || []).forEach((e) => {
        const li = document.createElement("li");
        li.textContent = `${e.start || "?"} · ${e.duration_s || 0}s · drop ${fmt(e.max_drop_c)} · ${e.end_reason || ""}`;
        recentEvents.appendChild(li);
      });
    }

    const calib = d.calibration;
    const calibStatus = document.getElementById("calibrationStatus");
    const areaMap = document.getElementById("areaMap");
    if (calibStatus) {
      calibStatus.textContent = calib
        ? `${calib.phase || ""} ${calib.seconds != null ? calib.seconds + "s" : ""}`
        : "";
    }
    if (areaMap) {
      if (calib && calib.area_map) {
        areaMap.style.display = "block";
        areaMap.textContent = calib.area_map;
      } else {
        areaMap.style.display = "none";
      }
    }

    setPreviewUi(d.preview || "off", d.preview_zoom);
  }

  function setPreviewUi(state, zoom) {
    previewState = state;
    if (previewStateEl) previewStateEl.textContent = `preview · ${state}`;
    if (previewToggle) {
      previewToggle.disabled = state === "disabled";
      previewToggle.textContent = state === "on" ? "Preview off" : "Preview on";
    }
    if (previewZoomEl) {
      const z = Number(zoom);
      const show = state === "on" && Number.isFinite(z);
      previewZoomEl.hidden = !show;
      if (show) previewZoomEl.textContent = `zoom ${z.toFixed(1)}×`;
    }
    if (state === "on") {
      startFramePoll();
      if (videoPlaceholder) videoPlaceholder.style.display = "none";
      if (videoFeed) videoFeed.style.display = "block";
    } else {
      stopFramePoll();
      clearImage();
      if (videoPlaceholder) videoPlaceholder.style.display = "flex";
      if (videoFeed) videoFeed.style.display = "none";
    }
  }

  function clearImage() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    if (videoFeed) videoFeed.removeAttribute("src");
  }

  function stopFramePoll() {
    if (frameTimer) {
      clearInterval(frameTimer);
      frameTimer = null;
    }
  }

  function startFramePoll() {
    if (frameTimer) return;
    frameTimer = setInterval(fetchFrame, 100);
    fetchFrame();
  }

  async function fetchFrame() {
    if (previewState !== "on") return;
    try {
      const res = await fetch("/api/preview/frame", { cache: "no-store" });
      if (res.status === 204 || !res.ok) return;
      const blob = await res.blob();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = URL.createObjectURL(blob);
      if (videoFeed) videoFeed.src = objectUrl;
    } catch (_) { /* ignore */ }
  }

  async function pollSnapshot() {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 3000);
    try {
      const res = await fetch("/api/snapshot", { signal: ctrl.signal, cache: "no-store" });
      clearTimeout(timer);
      if (!res.ok) throw new Error("bad");
      const data = await res.json();
      failCount = 0;
      setBanner(false);
      applySnapshot(data);
    } catch (_) {
      clearTimeout(timer);
      failCount += 1;
      if (failCount >= 2) setBanner(true, "Device not responding");
    }
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return res.json().catch(() => ({}));
  }

  if (previewToggle) {
    previewToggle.addEventListener("click", async () => {
      if (previewState === "disabled") return;
      const path = previewState === "on" ? "/api/preview/off" : "/api/preview/on";
      const data = await post(path, {});
      setPreviewUi(data.state || previewState);
    });
  }

  const snoozeButton = document.getElementById("snoozeButton");
  if (snoozeButton) snoozeButton.addEventListener("click", () => post("/api/snooze", {}));
  const calibrateButton = document.getElementById("calibrateButton");
  if (calibrateButton) calibrateButton.addEventListener("click", () => post("/api/calibrate", {}));
  const summaryButton = document.getElementById("summaryButton");
  if (summaryButton) summaryButton.addEventListener("click", () => post("/api/summary", {}));

  pollSnapshot();
  setInterval(pollSnapshot, 1000);
})();
