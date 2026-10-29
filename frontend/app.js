/**
 * ChainProof 链证 - 前端逻辑
 * 原生 JavaScript，无构建步骤。所有写入内容先转义再渲染。
 */
(() => {
  "use strict";

  const CONFIG = window.APP_CONFIG || {};
  const API_BASE = String(CONFIG.API_BASE || "http://127.0.0.1:5000/api").replace(
    /\/+$/,
    ""
  );
  const MAX_FILE_MB = Number(CONFIG.MAX_FILE_MB) || 10;
  const HASH_PATTERN = /^(?:0x)?[0-9a-fA-F]{64}$/;
  const UPLOAD_TIMEOUT_MS = 130000;

  const STATUS = {
    verified: {
      tone: "success",
      kicker: "INTEGRITY VERIFIED",
      title: "验证通过，文件完整",
      icon: "check",
      note: "链上摘要与本次计算的摘要完全一致，链下记录也与链上元数据一致。",
    },
    chain_only: {
      tone: "warning",
      kicker: "CHAIN PROOF FOUND",
      title: "文件完整，链下记录缺失",
      icon: "alert",
      note: "链上存在该哈希，但 MySQL 中缺少对应业务记录。文件完整性仍可证明，建议检查后端日志。",
    },
    inconsistent: {
      tone: "danger",
      kicker: "RECORD MISMATCH",
      title: "链上链下记录不一致",
      icon: "alert",
      note: "链上写入账户或时间戳与数据库保存值不一致。请检查数据库是否被直接修改。",
    },
    db_only: {
      tone: "danger",
      kicker: "ORPHANED DB RECORD",
      title: "链上未找到对应存证",
      icon: "alert",
      note: "不能仅凭数据库记录认定文件可信。请检查存证流程与链上状态。",
    },
    not_found: {
      tone: "neutral",
      kicker: "NO PROOF FOUND",
      title: "没有找到可信的存证",
      icon: "search",
      note: "如果文件应该已经存证，说明内容可能已被修改；如果从未存证，则无法找到记录。",
    },
  };

  const ICONS = {
    check: `<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m4 10.4 4 4L16.5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    alert: `<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 2.8 18 17H2L10 2.8Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M10 7.2v4.3M10 14.5v.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    search: `<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="9" cy="9" r="5" stroke="currentColor" stroke-width="1.5"/><path d="m13 13 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
    copy: `<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="5.2" y="5.2" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M10.8 5.2V4a1.3 1.3 0 0 0-1.3-1.3H4A1.3 1.3 0 0 0 2.7 4v5.5A1.3 1.3 0 0 0 4 10.8h1.2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`,
    file: `<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 2.5h5l3 3v8H4v-11Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M9 2.5v3h3M6 8h4M6 10.5h2.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const el = {};
  const state = {
    notarizeFile: null,
    verifyFile: null,
    activeTab: "notarize",
    busy: false,
    lastHealth: null,
    recordsLoaded: false,
  };
  let toastTimer = null;
  let healthTimer = null;

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    cacheElements();
    bindTabs();
    bindDropzones();
    bindForms();
    bindResultActions();
    bindRecordActions();
    restoreOperator();
    setYear();
    loadHealth();
    loadRecords();
    healthTimer = window.setInterval(loadHealth, 30000);
    window.addEventListener("beforeunload", () => {
      if (healthTimer) window.clearInterval(healthTimer);
    });
  }

  function cacheElements() {
    el.healthPill = $("#health-pill");
    el.healthText = $("#health-text");
    el.heroHash = $("#hero-hash");
    el.heroBlock = $("#hero-block");
    el.heroChain = $("#hero-chain");
    el.heroContract = $("#hero-contract");

    el.tabs = $$(".console-tab");
    el.panels = {
      notarize: $("#panel-notarize"),
      verify: $("#panel-verify"),
    };

    el.notarizeForm = $("#notarize-form");
    el.notarizeZone = $("#notarize-dropzone");
    el.notarizeInput = $("#notarize-input");
    el.notarizeEmpty = $("#notarize-empty");
    el.notarizeChip = $("#notarize-file");
    el.notarizeFilename = $("#notarize-filename");
    el.notarizeFilesize = $("#notarize-filesize");
    el.notarizeRemove = $("#notarize-remove");
    el.notarizeUser = $("#notarize-user");
    el.notarizeSubmit = $("#notarize-submit");
    el.notarizeProgress = $("#notarize-progress");
    el.notarizeProgressBar = $("#notarize-progress-bar");
    el.notarizeProgressText = $("#notarize-progress-text");

    el.verifyForm = $("#verify-form");
    el.verifyZone = $("#verify-dropzone");
    el.verifyInput = $("#verify-input");
    el.verifyEmpty = $("#verify-empty");
    el.verifyChip = $("#verify-file");
    el.verifyFilename = $("#verify-filename");
    el.verifyFilesize = $("#verify-filesize");
    el.verifyRemove = $("#verify-remove");
    el.verifyHash = $("#verify-hash");
    el.verifyUser = $("#verify-user");
    el.verifyHint = $("#verify-hint");
    el.verifySubmit = $("#verify-submit");
    el.verifyProgress = $("#verify-progress");
    el.verifyProgressBar = $("#verify-progress-bar");
    el.verifyProgressText = $("#verify-progress-text");

    el.resultSection = $("#result-section");
    el.resultCard = $("#result-card");

    el.recordsBody = $("#records-body");
    el.recordsCount = $("#records-count");
    el.refreshRecords = $("#refresh-records");

    el.toast = $("#toast");
    el.year = $("#year");

    el.maxFileLabels = $$("[data-max-file]");
    el.maxFileLabels.forEach((node) => {
      node.textContent = String(MAX_FILE_MB);
    });
    el.notarizeInput.tabIndex = -1;
    el.verifyInput.tabIndex = -1;
  }

  // ---------- 通用 UI ----------

  function toast(message, type = "info") {
    if (!el.toast) return;
    window.clearTimeout(toastTimer);
    el.toast.textContent = message;
    el.toast.className = "toast";
    if (type === "error") el.toast.classList.add("is-error");
    if (type === "success") el.toast.classList.add("is-success");
    el.toast.hidden = false;
    toastTimer = window.setTimeout(() => {
      el.toast.hidden = true;
    }, type === "error" ? 5200 : 3800);
  }

  function setBusy(button, busy, busyText) {
    if (!button) return;
    const label = button.querySelector(".button-label");
    if (busy) {
      if (label && !button.dataset.idleLabel) {
        button.dataset.idleLabel = label.textContent;
      }
      button.disabled = true;
      button.classList.add("is-busy");
      if (label && busyText) label.textContent = busyText;
    } else {
      button.disabled = false;
      button.classList.remove("is-busy");
      if (label && button.dataset.idleLabel) {
        label.textContent = button.dataset.idleLabel;
        delete button.dataset.idleLabel;
      }
    }
  }

  function showProgress(kind, visible) {
    const box = kind === "notarize" ? el.notarizeProgress : el.verifyProgress;
    if (!box) return;
    box.hidden = !visible;
    if (!visible) updateProgress(kind, 0, "");
  }

  function updateProgress(kind, percent, text) {
    const bar =
      kind === "notarize" ? el.notarizeProgressBar : el.verifyProgressBar;
    const label =
      kind === "notarize"
        ? el.notarizeProgressText
        : el.verifyProgressText;
    if (bar) bar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    if (label && text !== undefined) label.textContent = text;
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function formatDateTime(value) {
    if (!value) return "—";
    const numeric =
      typeof value === "number" || /^\d+$/.test(String(value))
        ? Number(value)
        : null;
    const date = new Date(
      numeric !== null && numeric < 1000000000000 ? numeric * 1000 : value
    );
    if (Number.isNaN(date.getTime())) return String(value);
    try {
      return new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      })
        .format(date)
        .replace(/\//g, "-");
    } catch {
      return date.toLocaleString();
    }
  }

  function shortHash(value, head = 10, tail = 8) {
    if (!value) return "—";
    const text = String(value);
    if (text.length <= head + tail + 1) return text;
    return `${text.slice(0, head)}…${text.slice(-tail)}`;
  }

  function shortAddress(value) {
    if (!value) return "—";
    const text = String(value);
    return text.length > 15 ? `${text.slice(0, 8)}…${text.slice(-6)}` : text;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => {
      switch (char) {
        case "&":
          return "&amp;";
        case "<":
          return "&lt;";
        case ">":
          return "&gt;";
        case '"':
          return "&quot;";
        case "'":
          return "&#39;";
        default:
          return char;
      }
    });
  }

  async function copyText(text) {
    const value = String(text ?? "");
    if (!value) return false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch {
      // 回退到 execCommand
    }
    try {
      const area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    } catch {
      return false;
    }
  }

  function validateFile(file) {
    if (!file) return "请选择文件";
    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      return `文件超过 ${MAX_FILE_MB} MB 上限，请选择更小的文件`;
    }
    return null;
  }

  function restoreOperator() {
    try {
      const saved = window.localStorage.getItem("chainproof_operator");
      if (saved && el.notarizeUser) el.notarizeUser.value = saved.slice(0, 40);
    } catch {
      // 隐私模式下 localStorage 可能不可用
    }
  }

  function saveOperator(value) {
    try {
      window.localStorage.setItem("chainproof_operator", value);
    } catch {
      // 忽略存储失败
    }
  }

  function setYear() {
    if (el.year) el.year.textContent = String(new Date().getFullYear());
  }

  // ---------- Tab ----------

  function bindTabs() {
    el.tabs.forEach((tab) => {
      tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    });
  }

  function switchTab(name) {
    if (!["notarize", "verify"].includes(name)) return;
    state.activeTab = name;
    el.tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    Object.entries(el.panels).forEach(([panelName, panel]) => {
      panel.hidden = panelName !== name;
    });
    if (name === "verify") {
      el.verifyHint.textContent = state.verifyFile
        ? "将优先查验已选择的文件；直接输入哈希会清除文件选择。"
        : "上传文件后系统会自动计算哈希；也可以直接粘贴已存证的哈希进行查询。";
    }
  }

  // ---------- 拖拽与文件选择 ----------

  function bindDropzones() {
    setupDropzone({
      kind: "notarize",
      zone: el.notarizeZone,
      input: el.notarizeInput,
      remove: el.notarizeRemove,
    });
    setupDropzone({
      kind: "verify",
      zone: el.verifyZone,
      input: el.verifyInput,
      remove: el.verifyRemove,
    });

    window.addEventListener("dragover", (event) => {
      if (event.dataTransfer?.types?.includes("Files")) event.preventDefault();
    });
    window.addEventListener("drop", (event) => {
      if (event.dataTransfer?.types?.includes("Files")) event.preventDefault();
    });
  }

  function setupDropzone({ kind, zone, input, remove }) {
    let depth = 0;
    const isVerify = kind === "verify";

    zone.addEventListener("click", (event) => {
      if (event.target === input) return;
      if (event.target.closest("button")) return;
      input.click();
    });

    zone.addEventListener("keydown", (event) => {
      if (event.target !== zone) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        input.click();
      }
    });

    zone.addEventListener("dragenter", (event) => {
      if (!event.dataTransfer?.types?.includes("Files")) return;
      event.preventDefault();
      depth += 1;
      zone.classList.add("is-dragover");
    });

    zone.addEventListener("dragover", (event) => {
      if (!event.dataTransfer?.types?.includes("Files")) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    });

    zone.addEventListener("dragleave", () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) zone.classList.remove("is-dragover");
    });

    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      depth = 0;
      zone.classList.remove("is-dragover");
      const file = event.dataTransfer?.files?.[0];
      if (!file) return;
      if (isVerify) {
        selectVerifyFile(file);
      } else {
        selectNotarizeFile(file);
      }
    });

    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) return;
      if (isVerify) {
        selectVerifyFile(file);
      } else {
        selectNotarizeFile(file);
      }
      // 允许再次选择同一个文件
      input.value = "";
    });

    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      if (isVerify) clearVerifyFile();
      else clearNotarizeFile();
    });
  }

  function setZoneFile(zone, hasFile) {
    zone.classList.toggle("has-file", hasFile);
    zone.setAttribute("aria-busy", "false");
  }

  function selectNotarizeFile(file) {
    const error = validateFile(file);
    if (error) {
      toast(error, "error");
      return;
    }
    state.notarizeFile = file;
    el.notarizeFilename.textContent = file.name;
    el.notarizeFilesize.textContent = `${formatBytes(file.size)} · 等待后端计算 SHA-256`;
    el.notarizeEmpty.hidden = true;
    el.notarizeChip.hidden = false;
    setZoneFile(el.notarizeZone, true);
  }

  function clearNotarizeFile() {
    state.notarizeFile = null;
    el.notarizeInput.value = "";
    el.notarizeFilename.textContent = "—";
    el.notarizeFilesize.textContent = "—";
    el.notarizeEmpty.hidden = false;
    el.notarizeChip.hidden = true;
    setZoneFile(el.notarizeZone, false);
  }

  function selectVerifyFile(file) {
    const error = validateFile(file);
    if (error) {
      toast(error, "error");
      return;
    }
    state.verifyFile = file;
    el.verifyFilename.textContent = file.name;
    el.verifyFilesize.textContent = `${formatBytes(file.size)} · 将由后端重新计算哈希`;
    el.verifyEmpty.hidden = true;
    el.verifyChip.hidden = false;
    setZoneFile(el.verifyZone, true);
    el.verifyHash.value = "";
    el.verifyHash.classList.remove("is-invalid");
    el.verifyHint.textContent = "将优先查验已选择的文件；直接输入哈希会清除文件选择。";
  }

  function clearVerifyFile(showHint = true) {
    state.verifyFile = null;
    el.verifyInput.value = "";
    el.verifyFilename.textContent = "—";
    el.verifyFilesize.textContent = "—";
    el.verifyEmpty.hidden = false;
    el.verifyChip.hidden = true;
    setZoneFile(el.verifyZone, false);
    if (showHint) {
      el.verifyHint.textContent =
        "上传文件后系统会自动计算哈希；也可以直接粘贴已存证的哈希进行查询。";
    }
  }

  // ---------- 表单提交 ----------

  function bindForms() {
    el.notarizeForm.addEventListener("submit", handleNotarizeSubmit);
    el.verifyForm.addEventListener("submit", handleVerifySubmit);

    el.notarizeUser.addEventListener("input", () => {
      el.notarizeUser.classList.remove("is-invalid");
    });
    el.verifyHash.addEventListener("input", () => {
      el.verifyHash.classList.remove("is-invalid");
      if (el.verifyHash.value.trim() && state.verifyFile) {
        clearVerifyFile(false);
        el.verifyHint.textContent = "已切换为哈希查询模式。";
      }
    });
  }

  async function handleNotarizeSubmit(event) {
    event.preventDefault();
    if (state.busy) return;

    const file = state.notarizeFile;
    const user = el.notarizeUser.value.trim();
    let invalid = false;

    if (!file) {
      toast("请先选择要存证的文件", "error");
      invalid = true;
    }
    if (!user) {
      el.notarizeUser.classList.add("is-invalid");
      el.notarizeUser.focus();
      toast("请填写操作人，便于链下审计", "error");
      invalid = true;
    }
    if (invalid) return;

    state.busy = true;
    setBusy(el.notarizeSubmit, true, "正在写入链上…");
    showProgress("notarize", true);
    updateProgress("notarize", 3, "正在计算哈希并上传…");
    el.resultSection.hidden = true;

    const formData = new FormData();
    formData.append("file", file, file.name);
    formData.append("user_name", user);
    saveOperator(user);

    try {
      const data = await uploadRequest(
        "/evidence",
        formData,
        (percent) => {
          if (percent >= 100) {
            updateProgress("notarize", 100, "文件已上传，正在等待链上确认…");
          } else {
            updateProgress("notarize", percent, `正在上传 ${percent}%…`);
          }
        }
      );
      updateProgress("notarize", 100, "已完成上链与落库");
      renderResult(data, "notarize");
      toast("存证成功，哈希已写入区块链", "success");
      clearNotarizeFile();
      await Promise.all([loadRecords(), loadHealth()]);
    } catch (error) {
      handleOperationError(error, "notarize");
    } finally {
      state.busy = false;
      setBusy(el.notarizeSubmit, false);
      window.setTimeout(() => showProgress("notarize", false), 900);
    }
  }

  async function handleVerifySubmit(event) {
    event.preventDefault();
    if (state.busy) return;

    const file = state.verifyFile;
    const hash = el.verifyHash.value.trim();
    const user = el.verifyUser.value.trim();

    if (!file && !hash) {
      el.verifyHash.classList.add("is-invalid");
      el.verifyHash.focus();
      toast("请上传文件，或粘贴一个 SHA-256 哈希", "error");
      return;
    }
    if (!file && !HASH_PATTERN.test(hash)) {
      el.verifyHash.classList.add("is-invalid");
      el.verifyHash.focus();
      toast("哈希格式不正确，应为 64 位十六进制字符", "error");
      return;
    }

    state.busy = true;
    setBusy(el.verifySubmit, true, file ? "正在重新计算哈希…" : "正在查询链上记录…");
    el.resultSection.hidden = true;

    try {
      let data;
      if (file) {
        showProgress("verify", true);
        updateProgress("verify", 5, "正在上传文件并计算哈希…");
        const formData = new FormData();
        formData.append("file", file, file.name);
        if (user) formData.append("user_name", user);
        data = await uploadRequest("/verify", formData, (percent) => {
          if (percent >= 100) {
            updateProgress("verify", 100, "文件已上传，正在比对链上摘要…");
          } else {
            updateProgress("verify", percent, `正在上传文件 ${percent}%…`);
          }
        });
      } else {
        data = await requestJson("/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hash, user_name: user || null }),
          timeout: 30000,
        });
      }

      renderResult(data, "verify");
      if (data.integrity_verified) {
        toast(
          data.status === "chain_only"
            ? "链上验证通过，但链下记录缺失"
            : "验证通过，文件自存证以来未被修改",
          data.status === "chain_only" ? "info" : "success"
        );
      } else {
        toast(data.message || "未通过完整性验证", "error");
      }
    } catch (error) {
      handleOperationError(error, "verify");
    } finally {
      state.busy = false;
      setBusy(el.verifySubmit, false);
      window.setTimeout(() => showProgress("verify", false), 700);
    }
  }

  function handleOperationError(error, mode) {
    const detail = error?.payload?.error?.detail;
    if (
      mode === "notarize" &&
      detail &&
      typeof detail === "object" &&
      detail.file_hash
    ) {
      renderResult(detail, "duplicate");
      toast(error.message || "该文件已有存证记录", "error");
      return;
    }
    toast(friendlyError(error), "error");
    if (error?.status === 404 && mode === "verify") {
      renderResult(
        {
          file_hash: el.verifyHash.value.trim(),
          exists_on_chain: false,
          exists_in_database: false,
          integrity_verified: false,
          status: "not_found",
          message: "未找到该哈希的存证记录",
        },
        "verify"
      );
    }
  }

  // ---------- API ----------

  class ApiError extends Error {
    constructor(message, payload, status) {
      super(message);
      this.name = "ApiError";
      this.payload = payload || null;
      this.status = status || 0;
    }
  }

  function parsePayload(xhr) {
    try {
      return JSON.parse(xhr.responseText || "{}");
    } catch {
      return null;
    }
  }

  function errorFromResponse(status, payload) {
    const message =
      payload?.error?.message ||
      (status === 0
        ? "请求失败，请检查后端服务"
        : `请求失败（HTTP ${status}）`);
    return new ApiError(message, payload, status);
  }

  function uploadRequest(path, formData, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}${path}`, true);
      xhr.timeout = UPLOAD_TIMEOUT_MS;
      xhr.setRequestHeader("Accept", "application/json");

      xhr.upload.addEventListener("progress", (event) => {
        if (!event.lengthComputable || typeof onProgress !== "function") return;
        const percent = Math.max(1, Math.round((event.loaded / event.total) * 100));
        onProgress(percent);
      });

      xhr.addEventListener("load", () => {
        const payload = parsePayload(xhr);
        if (xhr.status >= 200 && xhr.status < 300 && payload?.success !== false) {
          resolve(payload?.data ?? payload);
        } else {
          reject(errorFromResponse(xhr.status, payload));
        }
      });

      xhr.addEventListener("error", () => {
        reject(
          new ApiError(
            "无法连接后端，请确认 Flask 已在 5000 端口启动",
            null,
            0
          )
        );
      });

      xhr.addEventListener("timeout", () => {
        reject(
          new ApiError(
            "请求超时。若链上交易较慢，请稍后到存证记录中查询结果",
            null,
            0
          )
        );
      });

      xhr.send(formData);
    });
  }

  async function requestJson(path, options = {}) {
    const { timeout = 15000, headers = {}, ...rest } = options;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...rest,
        headers: { Accept: "application/json", ...headers },
        signal: controller.signal,
      });
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      if (!response.ok || payload?.success === false) {
        throw errorFromResponse(response.status, payload);
      }
      return payload?.data ?? payload;
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new ApiError("请求超时，请确认后端和本地链状态", null, 0);
      }
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        "无法连接后端，请确认 Flask 已在 5000 端口启动",
        null,
        0
      );
    } finally {
      window.clearTimeout(timer);
    }
  }

  function friendlyError(error) {
    if (error instanceof ApiError) {
      return error.message || "操作失败，请稍后重试";
    }
    if (error instanceof Error && error.message) return error.message;
    return "操作失败，请检查浏览器控制台与后端日志";
  }

  // ---------- 结果渲染 ----------

  function bindResultActions() {
    el.resultCard.addEventListener("click", async (event) => {
      if (event.target.closest("[data-close-result]")) {
        el.resultSection.hidden = true;
        el.resultCard.innerHTML = "";
        return;
      }
      const copyButton = event.target.closest("[data-copy]");
      if (copyButton) {
        const ok = await copyText(copyButton.dataset.copy || "");
        toast(ok ? "已复制到剪贴板" : "复制失败，请手动选择文本", ok ? "success" : "error");
      }
    });
  }

  function renderResult(data, mode) {
    if (!data) return;
    const statusKey = STATUS[data.status] ? data.status : "not_found";
    const statusInfo = STATUS[statusKey];

    let tone = statusInfo.tone;
    let kicker = statusInfo.kicker;
    let title = statusInfo.title;
    let message = data.message || statusInfo.message;
    let note = statusInfo.note;
    let icon = statusInfo.icon;

    if (mode === "notarize") {
      tone = "success";
      kicker = "NOTARY CONFIRMED";
      title = "存证成功，已写入区块链";
      message = "链上摘要与链下业务记录均已生成，可随时通过文件或哈希查验。";
      note = "请妥善保留原始文件。只有内容完全一致的文件，才能计算出相同的 SHA-256。";
      icon = "check";
    } else if (mode === "duplicate") {
      tone = "warning";
      kicker = "EXISTING PROOF FOUND";
      title = "该文件已有存证记录";
      message = data.message || "同一 SHA-256 已存在于链上，无需重复写入。";
      note = "可以直接使用下方哈希进行查验，或上传原始文件验证完整性。";
      icon = "alert";
    }

    const hash = data.file_hash || el.verifyHash.value.trim() || "—";
    const fileName = data.checked_file_name || data.file_name || "—";
    const block =
      data.block_number !== null && data.block_number !== undefined
        ? `#${data.block_number}`
        : "—";
    const chainTime = formatDateTime(data.chain_time || data.chain_timestamp);
    const user = data.user_name || (mode === "notarize" ? el.notarizeUser.value.trim() : "—");
    const owner = data.chain_owner || "—";
    const txHash = data.tx_hash || "—";
    const chainChip = data.exists_on_chain
      ? `<span class="result-chip is-on"><i></i>链上已存在</span>`
      : `<span class="result-chip"><i></i>链上未找到</span>`;
    const dbChip = data.exists_in_database
      ? `<span class="result-chip is-on"><i></i>链下记录存在</span>`
      : `<span class="result-chip"><i></i>链下无记录</span>`;
    const integrityChip = data.integrity_verified
      ? `<span class="result-chip is-on"><i></i>文件完整性通过</span>`
      : `<span class="result-chip"><i></i>文件完整性未通过</span>`;

    const fieldItems = [];
    if (data.status !== "not_found" || mode === "notarize" || mode === "duplicate") {
      fieldItems.push(resultItem("文件名", fileName));
      fieldItems.push(resultItem("操作人", user));
      fieldItems.push(resultItem("区块高度", block));
      fieldItems.push(resultItem("上链时间", chainTime));
      fieldItems.push(resultItem("链上写入账户", owner, "result-item-wide account-value"));
      if (txHash !== "—") {
        fieldItems.push(`
          <div class="result-item result-item-wide">
            <div class="result-item-top">
              <span>TRANSACTION HASH</span>
              <button class="inline-copy" type="button" data-copy="${escapeHtml(txHash)}">复制</button>
            </div>
            <code>${escapeHtml(txHash)}</code>
          </div>
        `);
      }
    }

    el.resultCard.className = `result-card is-${tone}`;
    el.resultCard.innerHTML = `
      <div class="result-head">
        <span class="status-mark">${ICONS[icon] || ICONS.check}</span>
        <div class="result-heading">
          <p class="result-kicker">${escapeHtml(kicker)}</p>
          <h3 class="result-title">${escapeHtml(title)}</h3>
          <p class="result-message">${escapeHtml(message)}</p>
        </div>
        <button class="result-close" type="button" data-close-result aria-label="关闭结果">×</button>
      </div>
      <div class="result-hash">
        <span class="result-hash-label">SHA-256 / FILE FINGERPRINT</span>
        <code>${escapeHtml(hash)}</code>
        <button class="copy-button" type="button" data-copy="${escapeHtml(hash)}" aria-label="复制文件哈希">
          ${ICONS.copy}
        </button>
      </div>
      <div class="result-chips">
        ${chainChip}
        ${dbChip}
        ${integrityChip}
      </div>
      ${
        fieldItems.length
          ? `<div class="result-grid">${fieldItems.join("")}</div>`
          : ""
      }
      <p class="result-footnote">${escapeHtml(note)}</p>
    `;

    el.resultSection.hidden = false;
    try {
      el.resultSection.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "nearest",
      });
    } catch {
      // 忽略滚动失败
    }
  }

  function resultItem(label, value, extraClass = "") {
    return `
      <div class="result-item ${extraClass}">
        <span>${escapeHtml(label)}</span>
        <strong title="${escapeHtml(value)}">${escapeHtml(value || "—")}</strong>
      </div>
    `;
  }

  // ---------- 记录列表 ----------

  function bindRecordActions() {
    el.refreshRecords.addEventListener("click", () => loadRecords());
    el.recordsBody.addEventListener("click", async (event) => {
      const copyButton = event.target.closest("[data-record-copy]");
      if (copyButton) {
        const ok = await copyText(copyButton.dataset.recordCopy || "");
        toast(ok ? "哈希已复制" : "复制失败", ok ? "success" : "error");
        return;
      }
      const verifyButton = event.target.closest("[data-verify-hash]");
      if (verifyButton) {
        const hash = verifyButton.dataset.verifyHash || "";
        switchTab("verify");
        clearVerifyFile(false);
        el.verifyHash.value = hash;
        el.verifyHash.classList.remove("is-invalid");
        el.verifyHint.textContent = "已从存证记录载入哈希，正在查验…";
        el.verifyUser.value = el.verifyUser.value || el.notarizeUser.value.trim();
        $("#workspace").scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth",
          block: "start",
        });
        await handleVerifySubmit(
          new Event("submit", { bubbles: false, cancelable: true })
        );
      }
    });
  }

  async function loadRecords() {
    if (!el.recordsBody) return;
    el.refreshRecords.disabled = true;
    el.recordsBody.innerHTML = `
      <tr class="table-placeholder">
        <td colspan="6"><span class="loading-dots" aria-hidden="true"><i></i><i></i><i></i></span>正在读取链下记录…</td>
      </tr>
    `;
    try {
      const data = await requestJson("/records?limit=8", { timeout: 12000 });
      const items = Array.isArray(data?.items) ? data.items : [];
      state.recordsLoaded = true;
      renderRecords(items);
      updateHeroFromRecords(items);
    } catch (error) {
      renderRecordsError(error);
    } finally {
      el.refreshRecords.disabled = false;
    }
  }

  function renderRecords(items) {
    if (!items.length) {
      el.recordsBody.innerHTML = `
        <tr class="table-placeholder">
          <td colspan="6">
            还没有存证记录。上传第一个文件，让哈希成为可信起点。
          </td>
        </tr>
      `;
      el.recordsCount.textContent = "0 条记录";
      return;
    }

    el.recordsBody.innerHTML = items
      .map((item) => {
        const name = item.file_name || "未命名文件";
        const user = item.user_name || "匿名";
        const hash = item.file_hash || "";
        const firstChar = Array.from(user)[0] || "?";
        const time = formatDateTime(item.chain_time || item.created_at);
        return `
          <tr>
            <td>
              <div class="file-cell">
                <span class="file-cell-icon">${ICONS.file}</span>
                <span title="${escapeHtml(name)}">${escapeHtml(name)}</span>
              </div>
            </td>
            <td>
              <button class="hash-copy" type="button" data-record-copy="${escapeHtml(hash)}" title="点击复制完整哈希">
                <code>${escapeHtml(shortHash(hash, 8, 6))}</code>
                ${ICONS.copy}
              </button>
            </td>
            <td>
              <div class="user-cell">
                <span class="user-avatar">${escapeHtml(firstChar)}</span>
                <span title="${escapeHtml(user)}">${escapeHtml(user)}</span>
              </div>
            </td>
            <td><span class="block-badge">#${escapeHtml(item.block_number ?? "—")}</span></td>
            <td><span class="time-cell">${escapeHtml(time)}</span></td>
            <td class="align-right">
              <button class="row-action" type="button" data-verify-hash="${escapeHtml(hash)}">查验</button>
            </td>
          </tr>
        `;
      })
      .join("");
    el.recordsCount.textContent = `最近 ${items.length} 条记录`;
  }

  function renderRecordsError(error) {
    el.recordsBody.innerHTML = `
      <tr class="table-placeholder">
        <td colspan="6">
          <span class="error-title">暂时无法读取存证记录</span>
          <span class="error-detail">${escapeHtml(friendlyError(error))}。请检查 MySQL 与后端服务后点击“刷新记录”。</span>
        </td>
      </tr>
    `;
    el.recordsCount.textContent = "读取失败";
  }

  function updateHeroFromRecords(items) {
    if (!items.length) {
      el.heroHash.textContent = "等待第一条存证写入…";
      return;
    }
    const latest = items[0];
    el.heroHash.textContent = latest.file_hash || "等待第一条存证写入…";
    if (latest.block_number !== null && latest.block_number !== undefined) {
      el.heroBlock.textContent = `#${latest.block_number}`;
    }
  }

  // ---------- 健康状态 ----------

  async function loadHealth() {
    try {
      const data = await requestJson("/health", { timeout: 10000 });
      state.lastHealth = data;
      updateHealthUI(data);
    } catch (error) {
      state.lastHealth = null;
      if (el.healthPill) {
        el.healthPill.dataset.state = "error";
        el.healthText.textContent = "后端未连接";
        el.healthPill.title = friendlyError(error);
      }
    }
  }

  function updateHealthUI(data) {
    const chain = data?.chain || {};
    const db = data?.database || {};
    const ok = Boolean(data?.ok);

    if (ok) {
      el.healthPill.dataset.state = "ok";
      el.healthText.textContent = "本地链已连接";
      el.healthPill.title = "Ganache、合约与 MySQL 连接正常";
    } else {
      el.healthPill.dataset.state = "warn";
      el.healthText.textContent = "服务待检查";
      const reasons = [];
      if (!chain.ok) reasons.push(`链：${chain.message || "异常"}`);
      if (!db.ok) reasons.push(`数据库：${db.message || "异常"}`);
      el.healthPill.title = reasons.join("；") || "部分服务未就绪";
    }

    if (chain.chain_id !== undefined) {
      el.heroChain.textContent = String(chain.chain_id);
    }
    if (chain.block_number !== undefined) {
      el.heroBlock.textContent = `#${chain.block_number}`;
    }
    if (chain.contract_address) {
      el.heroContract.textContent = shortAddress(chain.contract_address);
      el.heroContract.title = chain.contract_address;
    } else {
      el.heroContract.textContent = "未部署";
      el.heroContract.title = "请运行 python scripts/deploy.py";
    }
  }
})();
