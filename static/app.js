(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const state = {
    bootstrap: null,
    analysis: null,
    result: null,
    history: [],
    metadata: {},
    speakers: [],
    selectedPresetId: "",
    hospitalityMode: "omit",
    activeCommentTab: "part2",
    mappingSearch: "",
    busy: false,
  };

  const dropOriginal = { title: "", text: "" };

  const icons = {
    doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/></svg>',
    speaker: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="8" r="3"/><path d="M5 20c0-3.5 2.5-6 7-6s7 2.5 7 6"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12l4 4L19 6"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 4l9 16H3z"/><path d="M12 9v5M12 17h.01"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
    down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 4v12"/><path d="M7 11l5 5 5-5"/><path d="M4 20h16"/></svg>',
    zip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M6 3h12v18H6z"/><path d="M10 3v6h4V3"/><path d="M10 12h4M10 16h4"/></svg>',
    pdf: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 17v-4h2a1.5 1.5 0 0 1 0 3H9"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>',
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/></svg>',
    chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="15" height="15"><path d="M6 9l6 6 6-6"/></svg>',
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  function fmtBytes(bytes) {
    if (!bytes && bytes !== 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function toast(message, kind = "success") {
    const wrap = $("#toastWrap");
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.innerHTML = (kind === "error" ? icons.alert : kind === "success" ? icons.check : icons.info) + `<div>${esc(message)}</div>`;
    wrap.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(6px)";
      el.style.transition = "all .25s";
      setTimeout(() => el.remove(), 300);
    }, kind === "error" ? 7000 : 4500);
  }

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;
    const text = await response.text();
    if (text) {
      try { data = JSON.parse(text); } catch { data = { error: text }; }
    }
    if (!response.ok) throw new Error((data && data.error) || `Request failed (${response.status})`);
    return data;
  }

  function downloadUrl(runId, name) {
    return `/download/${encodeURIComponent(runId)}/${encodeURIComponent(name)}`;
  }

  function setBusy(flag, label = "") {
    state.busy = flag;
    const btn = $("#generateBtn");
    if (btn) {
      btn.disabled = flag;
      btn.innerHTML = flag ? `${icons.refresh} ${esc(label || "Working…")}` : `${icons.doc} Generate report package`;
    }
    const upload = $("#dropzone");
    if (upload) upload.classList.toggle("busy", flag);
  }

  function updateSteps(stage) {
    const steps = [$("#step1"), $("#step2"), $("#step3")];
    const activeIndex = stage === "verify" ? 1 : stage === "generate" ? 2 : 3;
    steps.forEach((step, index) => {
      step.className = "step";
      if (index < activeIndex || (stage === "done" && index <= 2)) step.classList.add("done");
      else if (index === activeIndex) step.classList.add("active");
    });
  }

  function setUploadStatus(title, text) {
    const dz = $("#dropzone");
    if (!dz) return;
    if (title) {
      if (!dropOriginal.title) dropOriginal.title = $("#dropTitle").textContent;
      if (!dropOriginal.text) dropOriginal.text = $("#dropText").textContent;
      $("#dropTitle").textContent = title;
      $("#dropText").textContent = text || "";
      dz.classList.add("busy");
    } else {
      if (dropOriginal.title) $("#dropTitle").textContent = dropOriginal.title;
      if (dropOriginal.text) $("#dropText").textContent = dropOriginal.text;
      dz.classList.remove("busy");
    }
  }

  function splitDisplay(display) {
    const text = String(display || "N/A");
    const match = text.match(/^(.*?)\s*\((.*)\)\s*$/);
    return match ? { mean: match[1], label: match[2] } : { mean: text, label: "" };
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                               */
  /* ------------------------------------------------------------------ */
  async function init() {
    bindEvents();
    try {
      const data = await api("/api/bootstrap");
      state.bootstrap = data;
      state.history = data.history || [];
      renderPresetOptions();
      renderHistory();
      const params = new URLSearchParams(window.location.search);
      const demo = params.get("demo");
      if (demo === "leap" || demo === "gfps") {
        await loadDemo(demo);
        if (params.get("generate") === "1" && state.analysis) await generate();
      }
    } catch (error) {
      toast(error.message, "error");
    }
  }

  function bindEvents() {
    $("#browseBtn").addEventListener("click", (event) => { event.stopPropagation(); $("#fileInput").click(); });
    $("#dropzone").addEventListener("click", () => $("#fileInput").click());
    $("#dropzone").addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("#fileInput").click(); }
    });
    $("#fileInput").addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (file) uploadFile(file);
      event.target.value = "";
    });
    ["dragenter", "dragover"].forEach((name) => {
      $("#dropzone").addEventListener(name, (event) => { event.preventDefault(); event.stopPropagation(); $("#dropzone").classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach((name) => {
      $("#dropzone").addEventListener(name, (event) => { event.preventDefault(); event.stopPropagation(); $("#dropzone").classList.remove("dragover"); });
    });
    $("#dropzone").addEventListener("drop", (event) => {
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) uploadFile(file);
    });
    $$(".sample-chip").forEach((button) => button.addEventListener("click", () => loadDemo(button.dataset.sample)));
    $("#changeFileBtn").addEventListener("click", () => $("#fileInput").click());
    $("#startOverBtn").addEventListener("click", startOver);
    $("#presetSelect").addEventListener("change", onPresetChange);
    $("#hospitalityMode").addEventListener("change", onHospitalityChange);
    $("#metaForm").addEventListener("input", (event) => {
      const key = event.target.name;
      if (!key) return;
      state.metadata[key] = event.target.value;
      if (key === "title") $("#wsTitle").textContent = event.target.value.trim() || "Untitled activity";
    });
    $("#speakerGrid").addEventListener("input", (event) => {
      const card = event.target.closest("[data-speaker-index]");
      if (!card) return;
      const index = Number(card.dataset.speakerIndex);
      const field = event.target.dataset.field;
      if (!field || !state.speakers[index]) return;
      state.speakers[index][field] = event.target.value;
    });
    $("#generateBtn").addEventListener("click", generate);
    $("#makePdf").addEventListener("change", (event) => { state.makePdf = event.target.checked; renderPlan(); });
    $("#refreshHistory").addEventListener("click", () => refreshHistory(true));
    $("#mappingSearch").addEventListener("input", (event) => {
      state.mappingSearch = event.target.value;
      renderMappingTable();
    });
    $("#saveActivityMapping").addEventListener("click", () => saveMapping("activity"));
    $("#saveSpeakerMapping").addEventListener("click", () => saveMapping("speaker"));
    $("#activityComments").addEventListener("click", (event) => {
      const tab = event.target.closest("[data-comment-tab]");
      if (!tab) return;
      state.activeCommentTab = tab.dataset.commentTab;
      renderActivityComments();
    });
    $("#resultBox").addEventListener("click", onResultAction);
    $("#historyList").addEventListener("click", onHistoryAction);
  }

  /* ------------------------------------------------------------------ */
  /* Upload / analyse                                                   */
  /* ------------------------------------------------------------------ */
  async function uploadFile(file) {
    if (!/\.csv$/i.test(file.name)) {
      toast("Choose a .csv export from Google Forms.", "error");
      return;
    }
    setUploadStatus("Reading your CSV…", "Detecting sections and recomputing values");
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await api("/api/analyze", { method: "POST", body: form });
      setAnalysis(data);
      toast("CSV analysed. Review the detected structure, then generate.", "success");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setUploadStatus(null);
    }
  }

  async function loadDemo(sample) {
    setUploadStatus("Loading the sample…", "Running the full detection pipeline");
    try {
      const data = await api("/api/demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample }),
      });
      setAnalysis(data);
      toast(sample === "leap" ? "LEAP sample loaded: 3 speaker reports detected." : "GFPS sample loaded: activity-only report.", "success");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setUploadStatus(null);
    }
  }

  function setAnalysis(data) {
    state.analysis = data;
    state.metadata = { ...(data.metadata || {}) };
    state.speakers = (data.speakers || []).map((speaker) => ({ ...speaker }));
    state.selectedPresetId = data.preset_id || "__none__";
    state.hospitalityMode = data.hospitality_mode || (data.detection.hospitality_column !== null ? "na" : "omit");
    state.activeCommentTab = (data.stats.activity.comments.part2 && data.stats.activity.comments.part2.count) ? "part2" : "part3";
    state.result = null;
    $("#heroView").hidden = true;
    $("#uploadCard").hidden = true;
    $("#workspace").hidden = false;
    updateSteps("verify");
    renderAll();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function startOver() {
    state.analysis = null;
    state.result = null;
    state.metadata = {};
    state.speakers = [];
    state.selectedPresetId = "";
    state.hospitalityMode = "omit";
    $("#heroView").hidden = false;
    $("#uploadCard").hidden = false;
    $("#workspace").hidden = true;
    $("#fileInput").value = "";
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function reanalyze({ presetId, hospitalityMode, preserve = false } = {}) {
    if (!state.analysis) return;
    const oldMeta = { ...state.metadata };
    const oldSpeakers = state.speakers.map((speaker) => ({ ...speaker }));
    const oldPreset = state.selectedPresetId;
    const oldMode = state.hospitalityMode;
    const payload = {
      upload_id: state.analysis.upload_id,
      preset_id: presetId !== undefined ? presetId : state.selectedPresetId,
      hospitality_mode: hospitalityMode !== undefined ? hospitalityMode : state.hospitalityMode,
      activity_mapping_id: state.analysis.mapping_ids.activity,
      speaker_mapping_id: state.analysis.mapping_ids.speaker,
    };
    setBusy(true, "Recomputing…");
    try {
      const data = await api("/api/reanalyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (preserve) {
        data.metadata = { ...data.metadata, ...oldMeta };
        data.speakers = (data.speakers || []).map((speaker, index) => ({
          ...speaker,
          name: oldSpeakers[index] ? oldSpeakers[index].name : speaker.name,
          topic: oldSpeakers[index] ? oldSpeakers[index].topic : speaker.topic,
        }));
      }
      data.upload_id = state.analysis.upload_id;
      data.available_presets = state.analysis.available_presets || (state.bootstrap ? state.bootstrap.presets : []);
      data.available_mappings = state.analysis.available_mappings || [];
      setAnalysis(data);
      if (presetId !== undefined && presetId !== "__none__") {
        state.selectedPresetId = presetId;
      } else if (presetId === "__none__") {
        state.selectedPresetId = "__none__";
      } else if (!preserve) {
        state.selectedPresetId = oldPreset;
      }
      if (hospitalityMode !== undefined) state.hospitalityMode = hospitalityMode;
      if (preserve) {
        // setAnalysis resets the form to the server's hospitality mode; keep the
        // user's requested mode when this was a hospitality-only change.
        state.hospitalityMode = hospitalModeForDisplay(hospitalityMode !== undefined ? hospitalityMode : oldMode, data);
      }
      renderAll();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function hospitalModeForDisplay(mode, data) {
    if (!data || data.detection.hospitality_column === null) return "omit";
    return mode || "na";
  }

  async function onPresetChange(event) {
    const presetId = event.target.value;
    state.selectedPresetId = presetId;
    await reanalyze({ presetId, preserve: false });
  }

  async function onHospitalityChange(event) {
    const mode = event.target.value;
    state.hospitalityMode = mode;
    await reanalyze({ hospitalityMode: mode, preserve: true });
  }

  /* ------------------------------------------------------------------ */
  /* Rendering                                                          */
  /* ------------------------------------------------------------------ */
  function renderAll() {
    if (!state.analysis) return;
    renderSummary();
    renderPresetOptions();
    renderChecks();
    renderMetadata();
    renderSpeakers();
    renderStats();
    renderMapping();
    renderPlan();
    renderControls();
    renderResult();
  }

  function renderSummary() {
    const a = state.analysis;
    const activity = a.stats.activity;
    const speakerCount = a.stats.speakers.length;
    $("#wsTitle").textContent = state.metadata.title || "Untitled activity";
    $("#wsFile").textContent = `${a.filename} · ${a.csv.rows} responses · ${a.csv.columns} columns`;
    const hospitality = activity.hospitality;
    let hospitalityLabel = "Hospitality omitted";
    let hospitalityClass = "muted";
    if (a.detection.hospitality_column !== null) {
      if (state.hospitalityMode === "compute") { hospitalityLabel = `Hospitality ${hospitality.mean_display} (${hospitality.interpretation})`; hospitalityClass = "gold"; }
      else if (state.hospitalityMode === "omit") { hospitalityLabel = "Hospitality row removed"; hospitalityClass = "muted"; }
      else { hospitalityLabel = "Hospitality N/A"; hospitalityClass = "gold"; }
    }
    const chips = [
      `<span class="chip"><i></i><strong>Activity report</strong></span>`,
      speakerCount
        ? `<span class="chip gold"><i></i><strong>${speakerCount}</strong> speaker report${speakerCount === 1 ? "" : "s"}</span>`
        : `<span class="chip muted"><i></i>No speaker reports</span>`,
      `<span class="chip ${hospitalityClass}"><i></i>${esc(hospitalityLabel)}</span>`,
      `<span class="chip"><i></i>N = <strong>${activity.n}</strong> activity respondents</span>`,
    ];
    $("#summaryChips").innerHTML = chips.join("");
    $("#nChip").innerHTML = `<i></i><span>N = ${activity.n}</span>`;
    const ready = a.validation.ready;
    $("#readyBadge").className = `chip ${ready ? "" : "red"}`;
    $("#readyBadge").innerHTML = `<i></i><span>${ready ? "Ready to generate" : "Needs attention"}</span>`;
  }

  function renderPresetOptions() {
    const select = $("#presetSelect");
    if (!select) return;
    const presets = (state.bootstrap && state.bootstrap.presets) || (state.analysis && state.analysis.available_presets) || [];
    const options = presets.map((preset) => `<option value="${esc(preset.id)}">${esc(preset.name || preset.id)}</option>`);
    options.push(`<option value="__none__">Generic · no preset</option>`);
    select.innerHTML = options.join("");
    const desired = state.selectedPresetId || (state.analysis && state.analysis.preset_id) || "__none__";
    select.value = desired;
    if (select.value !== desired) select.value = "__none__";
    const preset = presets.find((item) => item.id === select.value);
    $("#presetNote").textContent = preset
      ? (preset.notes || "Preset prefills metadata, signatories and speaker names.")
      : "Metadata and speaker names come from the CSV or are entered manually.";
  }

  function renderChecks() {
    const a = state.analysis;
    const checks = a.validation.checks || [];
    $("#validationSub").textContent = `${a.validation.respondents} activity respondents · ${a.detection.speaker_count} speaker block${a.detection.speaker_count === 1 ? "" : "s"} · ${Object.keys(a.stats.activity.items).filter((key) => !(key === "management.hospitality" && state.hospitalityMode === "omit")).length} criteria`;
    $("#checkList").innerHTML = checks.map((check) => {
      const icon = check.status === "ok" ? icons.check : check.status === "info" ? icons.info : icons.alert;
      return `<div class="check ${esc(check.status)}">
        <span class="check-dot">${icon}</span>
        <div><div class="check-label">${esc(check.label)}</div>${check.detail ? `<div class="check-detail">${esc(check.detail)}</div>` : ""}</div>
      </div>`;
    }).join("");
    const notes = a.anomaly_notes || [];
    const warnings = (a.warnings || []).filter((w) => !notes.some((note) => note.includes(w)));
    const blocks = [];
    if (notes.length) {
      blocks.push(`<div class="alert-note"><strong>Sample reconciliation</strong><ul>${notes.map((note) => `<li>${esc(note)}</li>`).join("")}</ul></div>`);
    }
    if (warnings.length) {
      blocks.push(`<div class="alert-note"><strong>Parser notes</strong><ul>${warnings.slice(0, 6).map((warning) => `<li>${esc(warning)}</li>`).join("")}</ul></div>`);
    }
    $("#anomalyBox").innerHTML = blocks.join("");
  }

  function renderMetadata() {
    const map = {
      metaTitle: "title",
      metaDate: "date",
      metaVenue: "venue",
      metaProponent: "proponent",
      preparedBy: "prepared_by",
      checkedBy: "checked_by",
      signatoryName: "signatory_name",
      signatoryRole: "signatory_role",
    };
    Object.entries(map).forEach(([id, key]) => {
      const element = document.getElementById(id);
      if (element && document.activeElement !== element) element.value = state.metadata[key] || "";
    });
  }

  function renderSpeakers() {
    const speakers = state.speakers;
    const stats = state.analysis.stats.speakers || [];
    $("#speakerCount").textContent = speakers.length ? `· ${speakers.length}` : "";
    $("#speakerEmpty").hidden = speakers.length > 0;
    $("#speakerGrid").hidden = speakers.length === 0;
    $("#speakerGrid").innerHTML = speakers.map((speaker, index) => {
      const stat = stats[index] || {};
      const nameMissing = !String(speaker.name || "").trim();
      return `<div class="speaker-card" data-speaker-index="${index}">
        <div class="speaker-card-head">
          <span class="speaker-num">${String(index + 1).padStart(2, "0")}</span>
          <strong>${esc(speaker.name || `Speaker ${index + 1}`)}</strong>
          <span class="chip" style="margin-left:auto"><i></i>N = ${stat.n || 0}</span>
        </div>
        <div class="field">
          <label>Resource person</label>
          <input data-field="name" value="${esc(speaker.name || "")}" placeholder="Full name" style="${nameMissing ? "border-color:var(--red)" : ""}">
        </div>
        <div class="field">
          <label>Topic / subject matter</label>
          <textarea data-field="topic" placeholder="Topic or session title">${esc(speaker.topic || "")}</textarea>
        </div>
      </div>`;
    }).join("");
  }

  function distribution(frequencies) {
    if (!frequencies || !frequencies.length) return "";
    const max = Math.max(...frequencies.map((f) => f.count), 1);
    return `<div class="dist">${frequencies.map((f) => {
      const opacity = f.count ? 0.35 + 0.65 * (f.count / max) : 0.15;
      return `<i class="${f.count ? "on" : ""}" style="opacity:${opacity.toFixed(2)}" title="${f.score}: ${f.count} response${f.count === 1 ? "" : "s"} (${f.percent}%)"></i>`;
    }).join("")}</div>`;
  }

  function renderStats() {
    const a = state.analysis.stats.activity;
    const overall = splitDisplay(a.overall_display);
    const criteriaCount = Object.keys(a.items).filter((key) => !(key === "management.hospitality" && state.hospitalityMode === "omit")).length;
    $("#statsSub").textContent = `${a.n} respondents contributed at least one valid activity rating. Each item's n excludes blanks and N/A.`;
    $("#overallMetrics").innerHTML = `
      <div class="metric">
        <div class="metric-label">Overall satisfaction</div>
        <div class="metric-value">${esc(overall.mean)} ${overall.label ? `<small>${esc(overall.label)}</small>` : ""}</div>
        <div class="metric-note">Mean of the two Overall Evaluation items</div>
      </div>
      <div class="metric">
        <div class="metric-label">Respondents</div>
        <div class="metric-value">${a.n}</div>
        <div class="metric-note">Consenting responses with activity ratings</div>
      </div>
      <div class="metric">
        <div class="metric-label">Criteria</div>
        <div class="metric-value">${criteriaCount}</div>
        <div class="metric-note">Part I rows in the template</div>
      </div>`;

    const mapping = state.analysis.mappings.activity;
    const groups = [];
    const groupMap = new Map();
    (mapping.items || []).forEach((spec) => {
      const groupName = spec.group || "Part I";
      if (!groupMap.has(groupName)) {
        const group = { name: groupName, items: [] };
        groupMap.set(groupName, group);
        groups.push(group);
      }
      groupMap.get(groupName).items.push(spec);
    });
    const rows = [];
    rows.push(`<thead><tr><th>Criterion</th><th class="num">n</th><th class="num">Mean</th><th>Rating</th><th>Distribution</th></tr></thead><tbody>`);
    groups.forEach((group) => {
      rows.push(`<tr class="group-row"><td colspan="5">${esc(group.name)}</td></tr>`);
      group.items.forEach((spec) => {
        const item = a.items[spec.key];
        if (!item) return;
        if (spec.key === "management.hospitality" && state.hospitalityMode === "omit") return;
        const display = spec.key === "management.hospitality" && state.hospitalityMode !== "compute"
          ? { ...item, mean_display: "N/A", interpretation: "N/A" }
          : item;
        rows.push(`<tr>
          <td>${esc(display.label || spec.label || spec.key)}</td>
          <td class="num">${display.n}</td>
          <td class="num"><span class="mean">${esc(display.mean_display)}</span></td>
          <td><span class="label-pill">${esc(display.interpretation)}</span></td>
          <td>${distribution(display.frequencies)}</td>
        </tr>`);
      });
    });
    rows.push(`</tbody>`);
    $("#activityStats").innerHTML = rows.join("");
    renderActivityComments();
    renderSpeakerStats();
  }

  function renderActivityComments() {
    const comments = state.analysis.stats.activity.comments || {};
    const part2 = comments.part2 || { count: 0, comments: [] };
    const part3 = comments.part3 || { count: 0, comments: [] };
    const active = state.activeCommentTab === "part3" ? "part3" : "part2";
    const group = active === "part3" ? part3 : part2;
    const tabs = `<div class="comments-tabs">
      <button class="tab-btn ${active === "part2" ? "active" : ""}" data-comment-tab="part2">Part II · ${part2.count} comment${part2.count === 1 ? "" : "s"}</button>
      <button class="tab-btn ${active === "part3" ? "active" : ""}" data-comment-tab="part3">Part III · ${part3.count} comment${part3.count === 1 ? "" : "s"}</button>
    </div>`;
    let body = "";
    if (group.comments && group.comments.length) {
      body = `<div class="comment-list">${group.comments.map((comment, index) => `
        <div class="comment-item"><span class="n">${String(index + 1).padStart(2, "0")}</span><div style="white-space:pre-line">${esc(comment)}</div></div>`).join("")}</div>`;
    } else {
      const sentence = active === "part3" ? state.analysis.stats.activity.part3_sentence : "No comments were provided.";
      body = `<div class="comment-list"><div class="empty-comments">${esc(sentence)}</div></div>`;
    }
    $("#activityComments").innerHTML = tabs + body;
  }

  function renderSpeakerStats() {
    const speakers = state.analysis.stats.speakers || [];
    if (!speakers.length) {
      $("#speakerStats").innerHTML = `<div class="empty-note">No speaker blocks were found, so there is no speaker breakdown.</div>`;
      return;
    }
    const topicMapping = state.analysis.mappings.speaker.topic_items || [];
    const resourceMapping = state.analysis.mappings.speaker.resource_items || [];
    $("#speakerStats").innerHTML = speakers.map((speaker, speakerIndex) => {
      const topic = splitDisplay(speaker.topic_display);
      const resource = splitDisplay(speaker.resource_display);
      const topicRows = topicMapping.map((spec) => {
        const item = speaker.topic_items[spec.key];
        if (!item) return "";
        return `<tr><td>${esc(item.label || spec.label)}</td><td class="num">${item.n}</td><td class="num"><strong>${esc(item.mean_display)}</strong></td><td><span class="label-pill">${esc(item.interpretation)}</span></td></tr>`;
      }).join("");
      const resourceRows = resourceMapping.map((spec) => {
        const item = speaker.resource_items[spec.key];
        if (!item) return "";
        return `<tr><td>${esc(item.label || spec.label)}</td><td class="num">${item.n}</td><td class="num"><strong>${esc(item.mean_display)}</strong></td><td><span class="label-pill">${esc(item.interpretation)}</span></td></tr>`;
      }).join("");
      const c = speaker.comments || {};
      return `<details class="speaker-stat">
        <summary>
          <span class="speaker-num">${String(speakerIndex + 1).padStart(2, "0")}</span>
          <span class="sum-main"><span class="sum-name">${esc(speaker.name)}</span><span class="sum-topic">${esc(speaker.topic || "No topic entered")}</span></span>
          <span class="sum-score">${esc(topic.mean)} <span>topic</span> · ${esc(resource.mean)} <span>resource</span></span>
          ${icons.chev}
        </summary>
        <div class="speaker-stat-body">
          <p class="small muted" style="margin:2px 0 8px">N = ${speaker.n} · Topic: ${esc(speaker.topic_display)} · Resource person: ${esc(speaker.resource_display)}</p>
          <table class="mini-table"><thead><tr><th>Topic / subject matter</th><th class="num">n</th><th class="num">Mean</th><th>Rating</th></tr></thead><tbody>${topicRows}</tbody></table>
          <div class="section-divider" style="margin:12px 0"></div>
          <table class="mini-table"><thead><tr><th>Resource person</th><th class="num">n</th><th class="num">Mean</th><th>Rating</th></tr></thead><tbody>${resourceRows}</tbody></table>
          <div class="comments-tabs" style="margin-top:12px">
            <span class="chip">Q1 · ${(c.q1 && c.q1.count) || 0}</span>
            <span class="chip">Q2 · ${(c.q2 && c.q2.count) || 0}</span>
            <span class="chip">Q3 · ${(c.q3 && c.q3.count) || 0}</span>
          </div>
        </div>
      </details>`;
    }).join("");
  }

  function renderMapping() {
    renderMappingTable();
    const inventory = state.analysis.csv.inventory || [];
    const mapped = inventory.filter((row) => row.kind !== "unmapped").length;
    $("#mappingCount").textContent = `${mapped} of ${inventory.length} columns mapped`;
    const preview = state.analysis.csv.preview_columns || [];
    const rows = state.analysis.csv.preview_rows || [];
    $("#previewCount").textContent = `· first ${rows.length} row${rows.length === 1 ? "" : "s"}`;
    $("#previewTable").innerHTML = `<table><thead><tr><th>#</th>${preview.map((col) => `<th title="${esc(col.header)}">${esc(col.label || col.header)}</th>`).join("")}</tr></thead><tbody>${rows.map((row, index) => `<tr><td class="muted">${index + 1}</td>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    $("#activityMappingJson").value = JSON.stringify(state.analysis.mappings.activity, null, 2);
    $("#speakerMappingJson").value = JSON.stringify(state.analysis.mappings.speaker, null, 2);
  }

  function renderMappingTable() {
    const container = $("#mappingTable");
    if (!container || !state.analysis) return;
    const query = (state.mappingSearch || "").trim().toLowerCase();
    const inventory = state.analysis.csv.inventory || [];
    const filtered = inventory.filter((row) => !query || row.header.toLowerCase().includes(query) || (row.label || "").toLowerCase().includes(query));
    container.innerHTML = `<table><thead><tr><th>#</th><th>CSV header</th><th>Mapped to</th><th>Kind</th></tr></thead><tbody>${filtered.map((row) => `
      <tr class="${row.kind === "unmapped" ? "unmapped" : ""}">
        <td>${row.index}</td>
        <td>${esc(row.header)}</td>
        <td>${esc(row.label || (row.kind === "unmapped" ? "—" : row.kind))}</td>
        <td><span class="kind">${esc(row.kind)}</span></td>
      </tr>`).join("")}</tbody></table>`;
  }

  function renderPlan() {
    const speakers = state.speakers;
    const items = [
      `<div class="plan-item">${icons.doc}<span><strong>Activity Report</strong> · every activity</span><span class="meta">DOCX</span></div>`,
    ];
    speakers.forEach((speaker, index) => {
      items.push(`<div class="plan-item">${icons.speaker}<span><strong>Speaker ${String(index + 1).padStart(2, "0")}</strong> · ${esc(speaker.name || "Unnamed")}</span><span class="meta">DOCX</span></div>`);
    });
    $("#planList").innerHTML = items.join("");
    $("#planSub").textContent = `${items.length} Word report${items.length === 1 ? "" : "s"} will be generated${state.makePdf ? " + PDFs" : ""}.`;
  }

  function renderControls() {
    const hasHospitality = state.analysis.detection.hospitality_column !== null;
    const select = $("#hospitalityMode");
    select.disabled = !hasHospitality;
    select.value = hasHospitality ? (state.hospitalityMode || "na") : "omit";
    const item = state.analysis.stats.activity.items["management.hospitality"];
    if (!hasHospitality) {
      $("#hospitalityNote").textContent = "No hotel/accommodation question in this form — the row will be removed.";
    } else if (select.value === "compute") {
      $("#hospitalityNote").textContent = `Computed from ${item ? item.n : 0} answers → ${item ? item.mean_display : "N/A"} (${item ? item.interpretation : "N/A"}).`;
    } else if (select.value === "omit") {
      $("#hospitalityNote").textContent = "The hotel row and its values will be removed from Part I.";
    } else {
      $("#hospitalityNote").textContent = `Keep the row and print N/A. ${item ? `${item.n} answer(s) were collected but are treated as not applicable.` : ""}`;
    }
    $("#makePdf").checked = !!state.makePdf;
    const pdfOk = !state.bootstrap || state.bootstrap.pdf_available !== false;
    $("#makePdf").disabled = !pdfOk;
    if (!pdfOk) {
      state.makePdf = false;
      $("#makePdf").checked = false;
      $("#pdfNote").textContent = "PDF export is unavailable on this machine; DOCX still works.";
    } else {
      $("#pdfNote").textContent = "Uses Word or LibreOffice on this machine";
    }
    if (!state.busy) {
      $("#generateBtn").disabled = false;
      $("#generateBtn").innerHTML = `${icons.doc} Generate report package`;
    }
  }

  function renderResult() {
    const box = $("#resultBox");
    if (!state.result) {
      box.innerHTML = "";
      return;
    }
    const result = state.result;
    const files = result.files || [];
    const hasPdf = files.some((file) => file.pdf);
    box.innerHTML = `
      <div class="result-banner">${icons.check}<div><strong>Package ready</strong><span>${files.length} Word report${files.length === 1 ? "" : "s"}${hasPdf ? " + PDFs" : ""} · N = ${result.n}</span></div></div>
      <a class="btn btn-primary btn-block" href="${downloadUrl(result.id, result.zip)}" download>${icons.zip} Download ZIP package</a>
      <div class="download-list" style="margin-top:10px">
        ${files.map((file) => `<a class="download-item" href="${downloadUrl(result.id, file.name)}" download>
          ${file.kind === "activity" ? icons.doc : icons.speaker}
          <span class="name">${esc(file.label || file.name)}</span>
          <span class="meta">${fmtBytes(file.size)}</span>
        </a>${file.pdf ? `<a class="download-item" href="${downloadUrl(result.id, file.pdf)}" download>${icons.pdf}<span class="name">${esc((file.label || file.name) + " · PDF")}</span><span class="meta">PDF</span></a>` : ""}`).join("")}
      </div>
      ${!hasPdf ? `<button class="btn btn-soft btn-block" style="margin-top:9px" data-action="create-pdfs">${icons.pdf} Create PDFs for this package</button>` : ""}
      <button class="btn btn-ghost btn-block" style="margin-top:7px" data-action="start-over">Start another activity</button>
    `;
  }

  function renderHistory() {
    const list = $("#historyList");
    if (!list) return;
    if (!state.history || !state.history.length) {
      list.innerHTML = `<div class="empty-note">No reports yet. Generated packages will appear here for re-download.</div>`;
      return;
    }
    list.innerHTML = state.history.slice(0, 8).map((run) => `
      <div class="history-item" data-run-id="${esc(run.id)}">
        <div class="history-top">
          <div><div class="history-title">${esc(run.title)}</div><div class="history-date">${esc(run.date || run.created_at)} · N = ${run.n}</div></div>
          <span class="chip" style="padding:4px 7px;font-size:9.5px">${run.speaker_count} spk</span>
        </div>
        <div class="history-actions">
          <a class="mini-link" href="${downloadUrl(run.id, run.zip)}" download>ZIP</a>
          <button class="mini-link" data-history-action="files">Files</button>
          ${run.pdf ? "" : `<button class="mini-link" data-history-action="pdf">Create PDFs</button>`}
        </div>
        <div class="history-files" hidden></div>
      </div>`).join("");
  }

  /* ------------------------------------------------------------------ */
  /* Actions                                                            */
  /* ------------------------------------------------------------------ */
  async function generate() {
    if (!state.analysis) return;
    if (!String(state.metadata.title || "").trim()) {
      toast("Enter the activity title before generating.", "error");
      $("#metaTitle").focus();
      return;
    }
    const missingSpeaker = state.speakers.find((speaker) => !String(speaker.name || "").trim());
    if (missingSpeaker) {
      toast("Every detected speaker needs a resource-person name.", "error");
      return;
    }
    state.busy = true;
    state.result = null;
    renderResult();
    updateSteps("generate");
    $("#progress").classList.add("on");
    $("#progressBar").style.width = "8%";
    $("#progressText").textContent = "Preparing the activity template…";
    setBusy(true, "Generating…");
    const stages = [
      [28, "Filling the Activity Report…"],
      [52, "Building speaker reports…"],
      [74, "Applying table values and comments…"],
      [90, "Packaging downloads…"],
    ];
    let stageIndex = 0;
    const timer = setInterval(() => {
      if (stageIndex >= stages.length) return;
      const [width, text] = stages[stageIndex++];
      $("#progressBar").style.width = `${width}%`;
      $("#progressText").textContent = text;
    }, 850);
    try {
      const payload = {
        upload_id: state.analysis.upload_id,
        preset_id: state.selectedPresetId === "__none__" ? "__none__" : state.selectedPresetId,
        metadata: state.metadata,
        speakers: state.speakers,
        hospitality: { mode: state.hospitalityMode },
        activity_mapping_id: state.analysis.mapping_ids.activity,
        speaker_mapping_id: state.analysis.mapping_ids.speaker,
        make_pdf: !!state.makePdf,
      };
      const result = await api("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.result = result;
      $("#progressBar").style.width = "100%";
      $("#progressText").textContent = "Done.";
      updateSteps("done");
      setTimeout(() => $("#progress").classList.remove("on"), 800);
      renderResult();
      toast("Report package generated.", "success");
      await refreshHistory(false);
      $("#resultBox").scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) {
      $("#progress").classList.remove("on");
      toast(error.message, "error");
    } finally {
      clearInterval(timer);
      setBusy(false);
    }
  }

  async function onResultAction(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "create-pdfs") {
      if (!state.result) return;
      button.disabled = true;
      button.textContent = "Creating PDFs…";
      try {
        const result = await api(`/api/history/${state.result.id}/pdf`, { method: "POST" });
        state.result = result;
        renderResult();
        await refreshHistory(false);
        toast("PDFs created.", "success");
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
        button.textContent = "Create PDFs for this package";
      }
    }
    if (button.dataset.action === "start-over") startOver();
  }

  async function refreshHistory(showToast = true) {
    try {
      const data = await api("/api/history");
      state.history = data.runs || [];
      renderHistory();
      if (showToast) toast("History refreshed.");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function onHistoryAction(event) {
    const button = event.target.closest("[data-history-action]");
    if (!button) return;
    const item = button.closest("[data-run-id]");
    const run = state.history.find((entry) => entry.id === item.dataset.runId);
    if (!run) return;
    if (button.dataset.historyAction === "pdf") {
      button.disabled = true;
      button.textContent = "Working…";
      try {
        await api(`/api/history/${run.id}/pdf`, { method: "POST" });
        await refreshHistory(false);
        toast("PDFs created for that package.", "success");
      } catch (error) {
        toast(error.message, "error");
        button.disabled = false;
        button.textContent = "Create PDFs";
      }
    }
    if (button.dataset.historyAction === "files") {
      const box = item.querySelector(".history-files");
      if (!box.hidden) { box.hidden = true; return; }
      box.innerHTML = `<div class="download-list" style="margin-top:7px">${(run.files || []).map((file) => `<a class="download-item" href="${downloadUrl(run.id, file.name)}" download>${file.kind === "activity" ? icons.doc : icons.speaker}<span class="name">${esc(file.label || file.name)}</span><span class="meta">DOCX</span></a>`).join("")}</div>`;
      box.hidden = false;
    }
  }

  async function saveMapping(kind) {
    const editor = kind === "activity" ? $("#activityMappingJson") : $("#speakerMappingJson");
    let data;
    try {
      data = JSON.parse(editor.value);
    } catch (error) {
      toast(`That JSON is invalid: ${error.message}`, "error");
      return;
    }
    const defaultId = `${data.id || kind}_copy`;
    const id = window.prompt("Save this mapping under a new id (letters, digits, - or _):", defaultId);
    if (!id) return;
    data.id = id.trim();
    if (!data.name) data.name = id;
    try {
      await api("/api/mappings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      toast(`Mapping saved as “${data.id}”. It is now available for future activities.`, "success");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
