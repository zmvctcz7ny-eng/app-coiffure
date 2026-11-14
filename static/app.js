/* DocEdit — interface */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const S = {
  doc: null,            // résumé du document ouvert
  items: new Map(),     // id -> élément {id, page, bbox, text, orig, edited, html}
  editing: null,        // id en cours de modification
  zoom: 1,
  scanPages: [],        // pages scannées validées [{blob, url}]
  stream: null,
  detectTimer: null,
  lastCorners: null,
  adj: null,            // {blob, url, corners, mode, w, h}
  installPrompt: null,
};

/* ------------------------------------------------------------------ utilitaires */

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new Error("Impossible de joindre DocEdit. Vérifiez que l'application est toujours lancée sur l'ordinateur et que vous êtes sur le même Wi-Fi.");
  }
  if (!res.ok) {
    let msg = "Une erreur s'est produite. Réessayez.";
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === "string" ? j.detail : msg; } catch (_) {}
    if (res.status === 413) msg = "Ce fichier est trop volumineux.";
    throw new Error(msg);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.blob();
}

const postJSON = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
});

let toastTimer;
function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), kind === "error" ? 7000 : 3500);
}

function loading(msg) {
  if (msg === false) return $("#loading").classList.add("hidden");
  $("#loadingMsg").textContent = msg || "Chargement…";
  $("#loading").classList.remove("hidden");
}

function show(view) {
  $$(".view").forEach(v => v.classList.toggle("active", v.id === view));
  window.scrollTo(0, 0);
}

function openSheet(id) {
  $$(".sheet").forEach(s => s.classList.add("hidden"));
  $("#sheetBack").classList.remove("hidden");
  $("#" + id).classList.remove("hidden");
}
function closeSheets() {
  $$(".sheet").forEach(s => s.classList.add("hidden"));
  $("#sheetBack").classList.add("hidden");
  S.editing = null;
}
$("#sheetBack").addEventListener("click", closeSheets);
$$("[data-close]").forEach(b => b.addEventListener("click", closeSheets));
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSheets(); });

const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ------------------------------------------------------------------ accueil */

$("#btnImport").addEventListener("click", () => $("#fileInput").click());
$("#fileInput").addEventListener("change", e => {
  const f = e.target.files[0];
  e.target.value = "";
  if (f) uploadFile(f);
});

// glisser-déposer
let dragDepth = 0;
window.addEventListener("dragenter", e => { e.preventDefault(); dragDepth++; document.body.classList.add("dragging"); });
window.addEventListener("dragleave", e => { e.preventDefault(); if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove("dragging"); } });
window.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("drop", e => {
  e.preventDefault(); dragDepth = 0; document.body.classList.remove("dragging");
  const f = e.dataTransfer && e.dataTransfer.files[0];
  if (f) uploadFile(f);
});

async function uploadFile(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const isImg = ["jpg", "jpeg", "png", "heic", "heif", "webp", "tif", "tiff"].includes(ext) || file.type.startsWith("image/");
  loading(isImg || ext === "pdf" ? "Ouverture et lecture du texte… Cela peut prendre quelques secondes." : "Ouverture du document…");
  try {
    const fd = new FormData();
    fd.append("file", file, file.name);
    const doc = await api("/api/upload", { method: "POST", body: fd });
    openDoc(doc);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    loading(false);
  }
}

async function checkResume() {
  const id = localStorage.getItem("docedit:last");
  const btn = $("#btnResume");
  if (!id) return btn.classList.add("hidden");
  try {
    const doc = await api("/api/doc/" + id);
    btn.textContent = "↩ Reprendre : " + doc.filename;
    btn.onclick = () => openDoc(doc);
    btn.classList.remove("hidden");
  } catch (_) {
    localStorage.removeItem("docedit:last");
    btn.classList.add("hidden");
  }
}

async function loadStatus() {
  try {
    const st = await api("/api/status");
    S.status = st;
    const w = $("#ocrWarning");
    if (st.ocr && st.ocr.message) { w.textContent = "ℹ️ " + st.ocr.message; w.classList.remove("hidden"); }
    else w.classList.add("hidden");
  } catch (_) {}
}

/* ------------------------------------------------------------------ installation (PWA) */

window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); S.installPrompt = e; });
const standalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
if (standalone()) $("#btnInstall").classList.add("hidden");
window.addEventListener("appinstalled", () => { $("#btnInstall").classList.add("hidden"); toast("DocEdit est installé !", "ok"); });

$("#btnInstall").addEventListener("click", async () => {
  if (S.installPrompt) {
    S.installPrompt.prompt();
    await S.installPrompt.userChoice.catch(() => {});
    S.installPrompt = null;
    return;
  }
  const ua = navigator.userAgent;
  let html;
  if (/iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) {
    html = `<ol><li>Ouvrez cette page dans <strong>Safari</strong>.</li>
      <li>Touchez le bouton <strong>Partager</strong> <span aria-hidden="true">(carré avec une flèche ⬆)</span>.</li>
      <li>Choisissez <strong>« Sur l'écran d'accueil »</strong>, puis <strong>Ajouter</strong>.</li></ol>`;
  } else if (/Android/.test(ua)) {
    html = `<ol><li>Dans <strong>Chrome</strong>, touchez le menu <strong>⋮</strong> en haut à droite.</li>
      <li>Choisissez <strong>« Ajouter à l'écran d'accueil »</strong> (ou « Installer l'application »).</li>
      <li>Confirmez avec <strong>Ajouter</strong>.</li></ol>`;
  } else {
    html = `<ol><li>Dans <strong>Chrome</strong> ou <strong>Edge</strong>, cliquez sur l'icône d'installation
      <span aria-hidden="true">(un écran avec une flèche ⊕)</span> à droite de la barre d'adresse,</li>
      <li>ou ouvrez le menu <strong>⋮</strong> → <strong>« Installer DocEdit »</strong> / « Applications » → « Installer ce site en tant qu'application ».</li>
      <li>Sur Mac avec Safari : menu <strong>Fichier → « Ajouter au Dock »</strong>.</li></ol>`;
  }
  if (!window.isSecureContext) {
    html += `<p class="muted small">Astuce : sur téléphone, l'adresse <strong>https://</strong> affichée au démarrage de DocEdit permet une installation complète
      (acceptez l'avertissement de sécurité une fois : c'est votre propre ordinateur).</p>`;
  }
  $("#installText").innerHTML = html;
  openSheet("installSheet");
});

$("#btnPhone").addEventListener("click", () => {
  const st = S.status || {};
  $("#qrImg").src = "/api/qr?ts=" + Date.now();
  $("#qrUrl").textContent = st.lan_url || location.origin;
  $("#httpsTip").innerHTML = st.lan_url_https
    ? `Pour utiliser la caméra en direct et installer l'appli, vous pouvez aussi ouvrir <code>${esc(st.lan_url_https)}</code> et accepter l'avertissement de sécurité (une seule fois).`
    : "";
  openSheet("phoneSheet");
});

/* ------------------------------------------------------------------ éditeur */

function openDoc(doc) {
  S.doc = doc;
  S.items = new Map(doc.items.map(it => [it.id, it]));
  localStorage.setItem("docedit:last", doc.id);
  $("#docName").textContent = doc.filename;
  const n = doc.pages.length;
  $("#docInfo").textContent = `${doc.kind_label} · ${n} ${doc.kind === "xlsx" ? (n > 1 ? "feuilles" : "feuille") : (n > 1 ? "pages" : "page")}`
    + (doc.lang ? ` · langue détectée : ${doc.lang}` : "");
  const banners = $("#banners");
  banners.innerHTML = "";
  for (const w of doc.warnings || []) banners.insertAdjacentHTML("beforeend", `<p class="notice">ℹ️ ${esc(w)}</p>`);
  if (!doc.items.length && doc.ocr_available !== false) {
    banners.insertAdjacentHTML("beforeend", `<p class="notice">Aucun texte n'a été trouvé dans ce document. S'il s'agit d'une photo,
      essayez de la reprendre plus nette, bien éclairée et de face.</p>`);
  }
  renderPages();
  updateCounters(doc);
  show("editor");
}

function pct(v, total) { return (100 * v / total).toFixed(4) + "%"; }

function placeBox(el, it, page) {
  const [x0, y0, x1, y1] = it.bbox;
  const padX = (y1 - y0) * 0.15, padY = (y1 - y0) * 0.12;
  el.style.left = pct(x0 - padX, page.w);
  el.style.top = pct(y0 - padY, page.h);
  el.style.width = pct(x1 - x0 + 2 * padX, page.w);
  el.style.height = pct(y1 - y0 + 2 * padY, page.h);
}

function renderPages() {
  const doc = S.doc;
  const wrap = $("#pages");
  wrap.innerHTML = "";
  wrap.classList.toggle("show-boxes", $("#chkBoxes").checked);
  for (const page of doc.pages) {
    if (doc.pages.length > 1) {
      const lab = document.createElement("div");
      lab.className = page.mode === "html" && page.title ? "sheet-tab" : "page-label";
      lab.textContent = page.mode === "html" && page.title ? "Feuille : " + page.title : `Page ${page.index + 1} / ${doc.pages.length}`;
      wrap.appendChild(lab);
    }
    const el = document.createElement("div");
    el.className = "page";
    el.dataset.page = page.index;
    if (page.mode === "html") {
      el.classList.add("htmlpage");
      if (page.cls) el.classList.add(page.cls);
      el.innerHTML = page.html;  // HTML produit par le serveur DocEdit (textes échappés)
      $$(".it", el).forEach(n => {
        const it = S.items.get(n.dataset.id);
        if (it && it.edited) n.classList.add("edited");
        n.tabIndex = 0;
      });
    } else {
      el.style.aspectRatio = `${page.w} / ${page.h}`;
      const img = document.createElement("img");
      img.className = "pimg";
      img.alt = `Page ${page.index + 1}`;
      img.loading = page.index < 2 ? "eager" : "lazy";
      img.src = `/api/doc/${doc.id}/page/${page.index}?v=${page.v}`;
      img.onerror = () => toast("Une page n'a pas pu être affichée. Rechargez la page.", "error");
      el.appendChild(img);
      const layer = document.createElement("div");
      layer.className = "layer";
      for (const it of S.items.values()) {
        if (it.page !== page.index || !it.bbox) continue;
        const b = document.createElement("div");
        b.className = "box" + (it.edited ? " edited" : "");
        b.dataset.id = it.id;
        b.tabIndex = 0;
        b.setAttribute("role", "button");
        b.setAttribute("aria-label", "Modifier : " + it.text);
        b.title = it.text;
        placeBox(b, it, page);
        layer.appendChild(b);
      }
      el.appendChild(layer);
    }
    wrap.appendChild(el);
  }
}

$("#pages").addEventListener("click", e => {
  const t = e.target.closest("[data-id]");
  if (t) openEdit(t.dataset.id);
});
$("#pages").addEventListener("keydown", e => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const t = e.target.closest("[data-id]");
  if (t) { e.preventDefault(); openEdit(t.dataset.id); }
});
$("#chkBoxes").addEventListener("change", e => $("#pages").classList.toggle("show-boxes", e.target.checked));

function setZoom(z) {
  S.zoom = Math.max(0.5, Math.min(2.5, z));
  document.documentElement.style.setProperty("--zoom", S.zoom);
}
$("#btnZoomIn").addEventListener("click", () => setZoom(S.zoom * 1.2));
$("#btnZoomOut").addEventListener("click", () => setZoom(S.zoom / 1.2));

function updateCounters(u) {
  $("#btnUndo").disabled = !u.can_undo;
  $("#btnRedo").disabled = !u.can_redo;
  const n = u.edited_count || 0;
  $("#editCount").textContent = n ? `${n} texte${n > 1 ? "s" : ""} modifié${n > 1 ? "s" : ""}` : "Touchez un texte pour le modifier";
}

function applyUpdate(u) {
  const doc = S.doc;
  for (const it of u.items || []) {
    S.items.set(it.id, it);
    $$(`[data-id="${CSS.escape(it.id)}"]`, $("#pages")).forEach(n => {
      n.classList.toggle("edited", !!it.edited);
      if (n.classList.contains("box")) {
        placeBox(n, it, doc.pages[it.page]);
        n.title = it.text;
        n.setAttribute("aria-label", "Modifier : " + it.text);
      } else if (it.html !== undefined) {
        n.innerHTML = it.html;
      }
    });
  }
  for (const p of u.pages || []) {
    const page = doc.pages[p.index];
    if (page.mode === "html") continue;
    page.v = p.v;
    const el = $(`.page[data-page="${p.index}"]`);
    const img = el && $("img.pimg", el);
    if (!img) continue;
    el.classList.add("loading-img");
    const next = new Image();
    next.onload = () => { img.src = next.src; el.classList.remove("loading-img"); };
    next.onerror = () => el.classList.remove("loading-img");
    next.src = `/api/doc/${doc.id}/page/${p.index}?v=${p.v}`;
  }
  updateCounters(u);
}

async function openEdit(id) {
  const it = S.items.get(id);
  if (!it) return;
  S.editing = id;
  $("#editOrig").textContent = it.orig;
  const ta = $("#editText");
  ta.value = it.text;
  ta.rows = it.multiline ? Math.min(8, Math.max(3, Math.ceil(it.text.length / 40))) : Math.min(4, Math.max(1, Math.ceil(it.text.length / 34)));
  $("#boldRow").classList.add("hidden");
  openSheet("editSheet");
  setTimeout(() => { ta.focus(); ta.select(); }, 60);
  const src = S.doc.kind;
  if (["image", "scan"].includes(src) || (src === "pdf" && S.doc.pages[it.page].mode === "image")) {
    try {
      const st = await api(`/api/doc/${S.doc.id}/item/${encodeURIComponent(id)}/style`);
      if (S.editing === id && st.bold !== null) {
        $("#editBold").checked = !!st.bold;
        $("#editBold").dataset.initial = st.bold ? "1" : "0";
        $("#boldRow").classList.remove("hidden");
      }
    } catch (_) {}
  }
}

async function saveEdit() {
  const id = S.editing;
  if (!id) return;
  const it = S.items.get(id);
  let text = $("#editText").value;
  if (!it.multiline) text = text.replace(/\s*\n\s*/g, " ");
  const body = { id, text };
  if (!$("#boldRow").classList.contains("hidden")) {
    const b = $("#editBold").checked;
    if ((b ? "1" : "0") !== $("#editBold").dataset.initial) body.bold = b;
  }
  closeSheets();
  if (text === it.text && body.bold === undefined) return;
  try {
    const u = await postJSON(`/api/doc/${S.doc.id}/edit`, body);
    applyUpdate(u);
  } catch (e) { toast(e.message, "error"); }
}
$("#editSave").addEventListener("click", saveEdit);
$("#editCancel").addEventListener("click", closeSheets);
$("#editRestore").addEventListener("click", () => {
  const it = S.items.get(S.editing);
  if (it) { $("#editText").value = it.orig; $("#editText").focus(); }
});
$("#editText").addEventListener("keydown", e => {
  const it = S.items.get(S.editing);
  if (e.key === "Enter" && !e.shiftKey && !(it && it.multiline)) { e.preventDefault(); saveEdit(); }
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); saveEdit(); }
});

async function undoRedo(which) {
  if (!S.doc) return;
  try {
    const u = await postJSON(`/api/doc/${S.doc.id}/${which}`);
    applyUpdate(u);
    if (u.changed) toast(which === "undo" ? "Modification annulée" : "Modification rétablie");
  } catch (e) { toast(e.message, "error"); }
}
$("#btnUndo").addEventListener("click", () => undoRedo("undo"));
$("#btnRedo").addEventListener("click", () => undoRedo("redo"));
document.addEventListener("keydown", e => {
  if (!$("#editor").classList.contains("active")) return;
  if (e.target.matches("input, textarea")) return;
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); undoRedo("undo"); }
  else if (mod && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) { e.preventDefault(); undoRedo("redo"); }
  else if (mod && (e.key.toLowerCase() === "f" || e.key.toLowerCase() === "h")) { e.preventDefault(); openSearch(); }
});

$("#edHome").addEventListener("click", () => { clearHits(); show("home"); checkResume(); });

/* Rechercher / Remplacer */
function clearHits() { $$(".hit").forEach(n => n.classList.remove("hit")); }
function openSearch() {
  $("#sResult").textContent = "";
  openSheet("searchSheet");
  setTimeout(() => $("#sQ").focus(), 60);
}
$("#btnSearch").addEventListener("click", openSearch);
$("#sClose").addEventListener("click", closeSheets);
const searchBody = () => ({ q: $("#sQ").value, r: $("#sR").value, case: $("#sCase").checked, word: $("#sWord").checked });
$("#sFind").addEventListener("click", async () => {
  clearHits();
  if (!$("#sQ").value) return toast("Indiquez le texte à rechercher.", "error");
  try {
    const res = await postJSON(`/api/doc/${S.doc.id}/search`, searchBody());
    res.ids.forEach(id => $$(`[data-id="${CSS.escape(id)}"]`, $("#pages")).forEach(n => n.classList.add("hit")));
    $("#sResult").textContent = res.count ? `${res.count} occurrence${res.count > 1 ? "s" : ""} trouvée${res.count > 1 ? "s" : ""} (surlignées en jaune).` : "Aucune occurrence trouvée.";
    if (res.ids.length) {
      const first = $(`[data-id="${CSS.escape(res.ids[0])}"]`, $("#pages"));
      closeSheets();
      if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
      toast($("#sResult").textContent);
    }
  } catch (e) { toast(e.message, "error"); }
});
$("#sReplace").addEventListener("click", async () => {
  clearHits();
  if (!$("#sQ").value) return toast("Indiquez le texte à rechercher.", "error");
  try {
    const u = await postJSON(`/api/doc/${S.doc.id}/replace`, searchBody());
    applyUpdate(u);
    closeSheets();
    toast(`${u.count} remplacement${u.count > 1 ? "s" : ""} effectué${u.count > 1 ? "s" : ""}.`, "ok");
  } catch (e) { $("#sResult").textContent = e.message; }
});
$("#sQ").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("#sR").focus(); } });
$("#sR").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("#sReplace").click(); } });

/* Export */
$("#btnExport").addEventListener("click", () => {
  const list = $("#exportList");
  list.innerHTML = "";
  S.doc.export_formats.forEach((f, i) => {
    list.insertAdjacentHTML("beforeend",
      `<label class="choice"><input type="radio" name="fmt" value="${esc(f.id)}" ${i === 0 ? "checked" : ""}> <span>${esc(f.label)}</span></label>`);
  });
  openSheet("exportSheet");
});
$("#exportCancel").addEventListener("click", closeSheets);
$("#exportGo").addEventListener("click", async () => {
  const fmt = ($("input[name=fmt]:checked") || {}).value || "original";
  closeSheets();
  loading("Préparation du fichier…");
  const url = `/api/doc/${S.doc.id}/export?fmt=${encodeURIComponent(fmt)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) {
      let msg = "Le fichier n'a pas pu être préparé. Réessayez.";
      try { msg = (await res.json()).detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    const name = m ? decodeURIComponent(m[1]) : "document";
    const file = new File([blob], name, { type: blob.type });
    // Sur mobile, le partage permet d'« Enregistrer dans Fichiers » / Photos
    if (navigator.canShare && navigator.canShare({ files: [file] }) && matchMedia("(hover: none)").matches) {
      try { await navigator.share({ files: [file], title: name }); loading(false); return; } catch (err) {
        if (err && err.name === "AbortError") { loading(false); return; }
      }
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
    toast("Téléchargement : " + name, "ok");
  } catch (e) {
    toast(e.message, "error");
  } finally { loading(false); }
});

/* ------------------------------------------------------------------ scanner */

$("#btnScan").addEventListener("click", openScanner);
$("#scanClose").addEventListener("click", () => {
  if (S.scanPages.length && !confirm("Abandonner les pages scannées ?")) return;
  stopCamera();
  S.scanPages.forEach(p => URL.revokeObjectURL(p.url));
  S.scanPages = [];
  renderThumbs();
  show("home");
});

async function openScanner() {
  show("scanner");
  renderThumbs();
  await startCamera();
}

async function startCamera() {
  const fallback = (why) => {
    $("#video").classList.add("hidden");
    $("#shutter").classList.add("hidden");
    $("#camFallback").classList.remove("hidden");
    $("#scanHint").textContent = why || "Prenez une photo de la feuille";
    $("#scanHint").classList.remove("ok");
  };
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) {
    return fallback("Prenez une photo de la feuille");
  }
  try {
    S.stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: "environment" }, width: { ideal: 3840 }, height: { ideal: 2160 } },
    });
  } catch (e) {
    const msg = e && e.name === "NotAllowedError"
      ? "Accès à la caméra refusé : autorisez-le dans les réglages du navigateur, ou prenez une photo."
      : "Caméra indisponible : prenez une photo à la place.";
    toast(msg, "error");
    return fallback();
  }
  $("#camFallback").classList.add("hidden");
  $("#video").classList.remove("hidden");
  $("#shutter").classList.remove("hidden");
  const v = $("#video");
  v.srcObject = S.stream;
  await v.play().catch(() => {});
  $("#scanHint").textContent = "Cadrez la feuille entière";
  startDetectLoop();
}

function stopCamera() {
  clearTimeout(S.detectTimer);
  S.detectTimer = null;
  if (S.stream) S.stream.getTracks().forEach(t => t.stop());
  S.stream = null;
  const c = $("#camOverlay");
  c.getContext("2d").clearRect(0, 0, c.width, c.height);
}

function videoRect() {
  const v = $("#video"), wrap = $("#camWrap").getBoundingClientRect();
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) return null;
  const k = Math.min(wrap.width / vw, wrap.height / vh);
  return { x: (wrap.width - vw * k) / 2, y: (wrap.height - vh * k) / 2, w: vw * k, h: vh * k, cw: wrap.width, ch: wrap.height };
}

function grabFrame(maxSide) {
  const v = $("#video");
  const k = maxSide ? Math.min(1, maxSide / Math.max(v.videoWidth, v.videoHeight)) : 1;
  const c = document.createElement("canvas");
  c.width = Math.round(v.videoWidth * k);
  c.height = Math.round(v.videoHeight * k);
  c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
  return new Promise(res => c.toBlob(res, "image/jpeg", maxSide ? 0.7 : 0.93));
}

function startDetectLoop() {
  const tick = async () => {
    if (!S.stream || !$("#scanner").classList.contains("active")) return;
    try {
      const blob = await grabFrame(640);
      if (blob) {
        const fd = new FormData();
        fd.append("file", blob, "frame.jpg");
        const r = await api("/api/scan/detect", { method: "POST", body: fd });
        drawLiveQuad(r.found ? r.corners : null);
        S.lastCorners = r.found ? r.corners : null;
      }
    } catch (_) { /* on réessaie au prochain tour */ }
    S.detectTimer = setTimeout(tick, 450);
  };
  S.detectTimer = setTimeout(tick, 300);
}

function drawLiveQuad(corners) {
  const c = $("#camOverlay"), r = videoRect();
  if (!r) return;
  const dpr = window.devicePixelRatio || 1;
  c.width = r.cw * dpr; c.height = r.ch * dpr;
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, r.cw, r.ch);
  const hint = $("#scanHint");
  if (!corners) { hint.textContent = "Cadrez la feuille entière"; hint.classList.remove("ok"); return; }
  hint.textContent = "Feuille détectée ✓ — prenez la photo";
  hint.classList.add("ok");
  g.beginPath();
  corners.forEach(([x, y], i) => { const px = r.x + x * r.w, py = r.y + y * r.h; i ? g.lineTo(px, py) : g.moveTo(px, py); });
  g.closePath();
  g.fillStyle = "rgba(74,222,128,.18)"; g.fill();
  g.lineWidth = 4; g.strokeStyle = "#4ade80"; g.stroke();
}

$("#shutter").addEventListener("click", async () => {
  if (!S.stream) return;
  const blob = await grabFrame(0);
  if (!blob) return toast("La photo n'a pas pu être prise. Réessayez.", "error");
  clearTimeout(S.detectTimer);
  goAdjust(blob);
});
$("#btnTakePhoto").addEventListener("click", () => $("#photoInput").click());
$("#btnPickPhoto").addEventListener("click", () => $("#photoPick").click());
["#photoInput", "#photoPick"].forEach(sel => $(sel).addEventListener("change", e => {
  const f = e.target.files[0];
  e.target.value = "";
  if (f) goAdjust(f);
}));

async function goAdjust(blob) {
  loading("Détection des bords de la feuille…");
  try {
    const fd = new FormData();
    fd.append("file", blob, blob.name || "photo.jpg");
    const r = await api("/api/scan/detect", { method: "POST", body: fd });
    if (S.adj && S.adj.url) URL.revokeObjectURL(S.adj.url);
    S.adj = { blob, url: URL.createObjectURL(blob), corners: r.corners, mode: S.adj ? S.adj.mode : "auto" };
    if (!r.found) toast("Les bords n'ont pas été trouvés automatiquement : placez les 4 coins sur la feuille.");
    $$("#modeSeg button").forEach(b => b.classList.toggle("on", b.dataset.mode === S.adj.mode));
    show("adjust");
    const img = $("#adjImg");
    img.onload = () => layoutAdjust();
    img.onerror = () => toast("Cette photo ne peut pas être affichée par le navigateur, mais elle sera traitée.", "error");
    img.src = S.adj.url;
  } catch (e) {
    toast(e.message, "error");
  } finally { loading(false); }
}

function layoutAdjust() {
  const img = $("#adjImg");
  img.style.width = img.style.height = "1px";
  const wrap = $("#adjWrap").getBoundingClientRect();
  const k = Math.min((wrap.width - 36) / img.naturalWidth, (wrap.height - 36) / img.naturalHeight, 1.5);
  img.style.width = img.naturalWidth * k + "px";
  img.style.height = img.naturalHeight * k + "px";
  $$(".handle", $("#adjStage")).forEach(h => h.remove());
  S.adj.corners.forEach((pt, i) => {
    const h = document.createElement("div");
    h.className = "handle";
    h.dataset.i = i;
    $("#adjStage").appendChild(h);
    dragHandle(h);
  });
  drawAdjust();
}
window.addEventListener("resize", () => { if ($("#adjust").classList.contains("active") && S.adj) layoutAdjust(); });

function drawAdjust() {
  const img = $("#adjImg");
  const w = img.clientWidth, h = img.clientHeight;
  $("#adjPoly").setAttribute("points", S.adj.corners.map(([x, y]) => `${x * w},${y * h}`).join(" "));
  $$(".handle", $("#adjStage")).forEach(el => {
    const [x, y] = S.adj.corners[+el.dataset.i];
    el.style.left = x * w + "px";
    el.style.top = y * h + "px";
  });
}

function dragHandle(el) {
  el.addEventListener("pointerdown", e => {
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    const move = ev => {
      const r = $("#adjImg").getBoundingClientRect();
      const x = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
      const y = Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height));
      S.adj.corners[+el.dataset.i] = [x, y];
      drawAdjust();
    };
    const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up); };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  });
}

$$("#modeSeg button").forEach(b => b.addEventListener("click", () => {
  S.adj.mode = b.dataset.mode;
  $$("#modeSeg button").forEach(x => x.classList.toggle("on", x === b));
}));

function backToCamera() {
  show("scanner");
  renderThumbs();
  if (S.stream) startDetectLoop(); else startCamera();
}
$("#adjBack").addEventListener("click", backToCamera);
$("#adjRetake").addEventListener("click", backToCamera);

$("#adjOk").addEventListener("click", async () => {
  loading("Recadrage et amélioration de la page…");
  try {
    const fd = new FormData();
    fd.append("file", S.adj.blob, S.adj.blob.name || "photo.jpg");
    fd.append("corners", JSON.stringify(S.adj.corners));
    fd.append("mode", S.adj.mode);
    const out = await api("/api/scan/process", { method: "POST", body: fd });
    S.scanPages.push({ blob: out, url: URL.createObjectURL(out) });
    toast(`Page ${S.scanPages.length} ajoutée. Scannez la suivante ou touchez « Terminer ».`, "ok");
    backToCamera();
  } catch (e) {
    toast(e.message, "error");
  } finally { loading(false); }
});

function renderThumbs() {
  const t = $("#thumbs");
  t.innerHTML = "";
  S.scanPages.forEach((p, i) => {
    const d = document.createElement("div");
    d.className = "th";
    d.innerHTML = `<img src="${p.url}" alt="Page ${i + 1}"><b title="Retirer">✕</b>`;
    d.querySelector("b").addEventListener("click", () => {
      if (!confirm(`Retirer la page ${i + 1} ?`)) return;
      URL.revokeObjectURL(p.url);
      S.scanPages.splice(i, 1);
      renderThumbs();
    });
    t.appendChild(d);
  });
  const n = S.scanPages.length;
  $("#scanDone").disabled = n === 0;
  $("#scanDone").textContent = n ? `Terminer (${n})` : "Terminer";
}

$("#scanDone").addEventListener("click", async () => {
  if (!S.scanPages.length) return;
  stopCamera();
  loading(`Lecture du texte de ${S.scanPages.length > 1 ? S.scanPages.length + " pages" : "la page"}…`);
  try {
    const fd = new FormData();
    S.scanPages.forEach((p, i) => fd.append("files", p.blob, `page_${i + 1}.jpg`));
    const doc = await api("/api/scan/finish", { method: "POST", body: fd });
    S.scanPages.forEach(p => URL.revokeObjectURL(p.url));
    S.scanPages = [];
    openDoc(doc);
  } catch (e) {
    toast(e.message, "error");
    show("scanner");
    startCamera();
  } finally { loading(false); }
});

/* ------------------------------------------------------------------ démarrage */

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
loadStatus();
checkResume();
