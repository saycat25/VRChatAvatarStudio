"use strict";
/* Interface do VRChat Avatar Studio: formulários gerados a partir do esquema do servidor. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}

const API = (url, body) => fetch(url, {
  method: "POST", headers: { "Content-Type": "application/json", "X-Studio": "1" }, body: JSON.stringify(body || {}),
});

let META = null, state = null, viewer = null, selected = null, busy = false, pending = false, timer = null;
let hiddenLayers = new Set(), weights = {}, exprKey = "", firstModel = true, partSeq = 0;
let undoStack = [], redoStack = [], historyCurrent = null, historyTimer = null;
const controls = {};   // chave -> função que atualiza o controle a partir do estado

function toast(msg, ms = 3800) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, ms);
}

// ------------------------------------------------------------------ estado

function clone(o) { return JSON.parse(JSON.stringify(o)); }

function persist() {
  try { localStorage.setItem("vas.state", JSON.stringify(state)); } catch (e) { /* cota/privado: ignora */ }
}

function updateHistoryButtons() {
  if (document.getElementById("btnUndo")) $("#btnUndo").disabled = undoStack.length === 0;
  if (document.getElementById("btnRedo")) $("#btnRedo").disabled = redoStack.length === 0;
}

function commitHistory() {
  clearTimeout(historyTimer);
  if (!state) return;
  const snapshot = JSON.stringify(state);
  if (historyCurrent == null) historyCurrent = snapshot;
  else if (snapshot !== historyCurrent) {
    undoStack.push(historyCurrent);
    if (undoStack.length > 60) undoStack.shift();
    redoStack = [];
    historyCurrent = snapshot;
  }
  updateHistoryButtons();
}

function scheduleHistory() {
  clearTimeout(historyTimer);
  historyTimer = setTimeout(commitHistory, 320);
}

function applyHistory(snapshot) {
  state = normalizeState(JSON.parse(snapshot));
  historyCurrent = JSON.stringify(state);
  selected = state.parts.length ? state.parts[0].id : null;
  syncControls(); renderParts(); persist(); updateHistoryButtons(); schedule(false);
}

function undo() {
  commitHistory();
  if (!undoStack.length) return;
  redoStack.push(JSON.stringify(state));
  applyHistory(undoStack.pop());
}

function redo() {
  commitHistory();
  if (!redoStack.length) return;
  undoStack.push(JSON.stringify(state));
  applyHistory(redoStack.pop());
}

function newId() { partSeq += 1; return "p" + Date.now().toString(36) + partSeq; }

function normalizeState(data) {
  const s = Object.assign(clone(META.defaults), data || {});
  s.parts = (Array.isArray(s.parts) ? s.parts : []).map((p) => Object.assign({ id: newId() }, p));
  const seen = new Set();
  for (const p of s.parts) { while (seen.has(p.id)) p.id += "x"; seen.add(p.id); }
  return s;
}

function schedule(trackHistory = true) {
  persist();
  if (trackHistory) scheduleHistory();
  clearTimeout(timer); timer = setTimeout(refresh, 90);
}

async function refresh() {
  if (busy) { pending = true; return; }
  busy = true;
  const spin = setTimeout(() => { $("#busy").hidden = false; }, 350);
  try {
    const r = await API("/api/model", { spec: state });
    const model = await r.json();
    if (!r.ok) throw new Error(model.error || "erro");
    viewer.setModel(model, !firstModel); firstModel = false;
    for (const n of hiddenLayers) viewer.setHidden(n, true);
    viewer.setWeights(weights);
    renderStats(model); renderLayers(model); renderIssues(model); renderExpr();
    $("#partBadge").textContent = state.parts.length;
  } catch (e) {
    toast("Não foi possível atualizar: " + e.message, 6000);
  } finally {
    clearTimeout(spin); $("#busy").hidden = true; busy = false;
    if (pending) { pending = false; refresh(); }
  }
}

// ------------------------------------------------------------------ aba Aparência

function mkField(it) {
  const k = it.key; let input, out, row;
  const set = (v) => { state[k] = v; schedule(); };
  if (it.type === "range" || it.type === "int") {
    input = h("input", { type: "range", min: it.min, max: it.max, step: it.step || 1, id: "f_" + k });
    out = h("output", { for: "f_" + k });
    input.addEventListener("input", () => { const v = parseFloat(input.value); out.textContent = v; set(v); });
    controls[k] = (v) => { input.value = v; out.textContent = v; };
    row = h("div", { class: "field" }, h("label", { for: "f_" + k }, it.label), input, out);
  } else if (it.type === "bool") {
    input = h("input", { type: "checkbox", id: "f_" + k });
    input.addEventListener("change", () => set(input.checked));
    controls[k] = (v) => { input.checked = !!v; };
    row = h("div", { class: "field check" }, input, h("label", { for: "f_" + k }, it.label));
  } else if (it.type === "select") {
    input = h("select", { id: "f_" + k }, it.options.map(([v, l]) => h("option", { value: v }, l)));
    input.addEventListener("change", () => set(input.value));
    controls[k] = (v) => { input.value = String(v); };
    row = h("div", { class: "field simple" }, h("label", { for: "f_" + k }, it.label), input);
  } else if (it.type === "color") {
    input = h("input", { type: "color", id: "f_" + k });
    input.addEventListener("input", () => set(input.value));
    controls[k] = (v) => { input.value = v; };
    row = h("div", { class: "field simple" }, h("label", { for: "f_" + k }, it.label), input);
  } else {
    input = h("input", { type: "text", id: "f_" + k, maxlength: 40 });
    input.addEventListener("input", () => set(input.value));
    controls[k] = (v) => { input.value = v; };
    row = h("div", { class: "field simple" }, h("label", { for: "f_" + k }, it.label), input);
  }
  return row;
}

function buildLook() {
  const root = $("#tab-look");
  for (const g of META.schema) {
    root.append(h("div", { class: "card" }, h("h3", null, g.group), g.items.map(mkField)));
  }
}

const STYLE_PRESETS = {
  anime: { hair_style: "long", ears: "human", tail: "none", top: "hoodie", bottom: "skirt", shoes: "sneakers",
    head_size: 1.22, eye_size: 1.18, detail: 3,
    skin: "#f3d1bf", hair: "#49345f", eyes: "#72aee8", top_color: "#e9e1f3",
    bottom_color: "#51415f", shoes_color: "#ee91b8", accent: "#f5b5d1" },
  kawaii: { hair_style: "twintails", ears: "cat", tail: "cat", top: "tshirt", bottom: "skirt", shoes: "sneakers",
    head_size: 1.24, eye_size: 1.24, detail: 3,
    skin: "#f7d9ca", hair: "#dc83b4", eyes: "#78b9e8", top_color: "#fff0f6",
    bottom_color: "#f0b9d3", shoes_color: "#ffffff", accent: "#f4a9cf" },
  streetwear: { hair_style: "bob", ears: "human", tail: "none", top: "hoodie", bottom: "pants", shoes: "sneakers",
    head_size: 1.15, eye_size: 1.08, detail: 3,
    skin: "#d9aa8e", hair: "#282532", eyes: "#8ca7d5", top_color: "#303746",
    bottom_color: "#252b3a", shoes_color: "#e6e8ee", accent: "#91c6d9" },
  fantasy: { hair_style: "long", ears: "elf", tail: "fox", top: "longsleeve", bottom: "skirt", shoes: "boots",
    detail: 3, skin: "#f0d2bd", hair: "#8e5bd6", eyes: "#39a9d6", top_color: "#f4e4ff",
    bottom_color: "#573b82", shoes_color: "#4c315f", accent: "#ffd16b" },
  futuristic: { hair_style: "spiky", ears: "cat", tail: "none", top: "hoodie", bottom: "pants", shoes: "boots", glasses: true, headphones: true,
    detail: 3, skin: "#d9c9e9", hair: "#33c6d5", eyes: "#b14be5", top_color: "#25283c",
    bottom_color: "#34394f", shoes_color: "#36a6bf", accent: "#f35eae" },
};
const PALETTE_KEYS = ["skin", "hair", "eyes", "top_color", "bottom_color", "shoes_color", "accent"];

function applyStyle(name) {
  const preset = STYLE_PRESETS[name];
  if (!preset) return;
  Object.assign(state, preset); syncControls(); schedule();
  toast("Visual " + name + " aplicado. Você pode ajustar cada detalhe depois.");
}

function savedPalettes() {
  try {
    const value = JSON.parse(localStorage.getItem("vas.palettes") || "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch (e) { return {}; }
}

function renderPalettes() {
  const select = $("#paletteSelect"), palettes = savedPalettes(), previous = select.value;
  select.textContent = "";
  const names = Object.keys(palettes).sort((a, b) => a.localeCompare(b, "pt-BR"));
  if (!names.length) select.append(h("option", { value: "" }, "Nenhuma paleta salva"));
  for (const name of names) select.append(h("option", { value: name }, name));
  if (names.includes(previous)) select.value = previous;
  $("#paletteApply").disabled = names.length === 0;
}

function savePalette() {
  const name = (prompt("Nome para esta paleta de cores:") || "").trim().slice(0, 40);
  if (!name) return;
  const palettes = savedPalettes();
  palettes[name] = Object.fromEntries(PALETTE_KEYS.map((key) => [key, state[key]]));
  try { localStorage.setItem("vas.palettes", JSON.stringify(palettes)); }
  catch (e) { toast("Não foi possível salvar: armazenamento do navegador cheio.", 6000); return; }
  renderPalettes(); $("#paletteSelect").value = name; toast("Paleta '" + name + "' salva neste navegador.");
}

function applyPalette() {
  const name = $("#paletteSelect").value, palette = savedPalettes()[name];
  if (!palette) return;
  for (const key of PALETTE_KEYS) if (palette[key]) state[key] = palette[key];
  syncControls(); schedule(); toast("Paleta '" + name + "' aplicada.");
}

function syncControls() {
  for (const [k, fn] of Object.entries(controls)) fn(state[k]);
}

// ------------------------------------------------------------------ painéis de resultado

const RCOL = ["var(--ok)", "var(--good)", "var(--warn)", "var(--bad)", "var(--vbad)"];

function renderStats(model) {
  const chip = $("#rankChip");
  chip.textContent = model.rank; chip.className = "chip r" + model.rankIndex;
  const box = $("#statRows"); box.textContent = "";
  for (const r of model.rows) {
    const cap = r.limits[3], pct = Math.min(100, (r.value / cap) * 100);
    box.append(h("div", { class: "stat" },
      h("div", { class: "l" }, h("span", null, r.label), h("span", null, r.value.toLocaleString("pt-BR") + " / " + cap.toLocaleString("pt-BR"))),
      h("div", { class: "bar" }, h("i", { style: `width:${pct}%;background:${RCOL[r.rank]}` }))));
  }
}

function renderLayers(model) {
  const box = $("#layers"); box.textContent = "";
  for (const m of model.meshes) {
    const cb = h("input", { type: "checkbox" }); cb.checked = !hiddenLayers.has(m.name);
    cb.addEventListener("change", () => {
      if (cb.checked) hiddenLayers.delete(m.name); else hiddenLayers.add(m.name);
      viewer.setHidden(m.name, !cb.checked);
    });
    box.append(h("div", { class: "layer" }, h("label", null, cb, m.label), h("small", null, m.tris.toLocaleString("pt-BR") + " tri")));
  }
}

function renderIssues(model) {
  const ul = $("#issues"); ul.textContent = "";
  const items = [];
  for (const e of model.errors) items.push(["e", e]);
  for (const w of model.warnings) items.push(["w", w]);
  if (model.rankIndex >= 2) {
    const names = { skinned_meshes: "malhas", material_slots: "materiais", triangles: "triângulos", bones: "ossos",
      physbone_components: "PhysBones", physbone_transforms: "ossos de PhysBone" };
    items.push(["w", "Ranking " + model.rank + ": reduza " + model.why.map((k) => names[k] || k).join(", ") +
      ". Dica: agrupe peças no mesmo grupo ou ative \"Juntar tudo em 1 malha\"."]);
  }
  $("#issuesCard").hidden = items.length === 0;
  for (const [c, t] of items) ul.append(h("li", { class: c }, t));
}

const EXPR = [["Blink", "Piscar"], ["Smile", "Sorriso"], ["Angry", "Bravo"], ["Sad", "Triste"], ["Surprised", "Surpresa"],
  ["Blush", "Rubor"], ["LookUp", "Olhar ↑"], ["LookDown", "Olhar ↓"]];

function renderExpr() {
  const names = new Set(); viewer.meshes.forEach((m) => m.shapes.forEach((s) => names.add(s.name)));
  const key = Array.from(names).join(",");
  if (key === exprKey) return; exprKey = key;
  const box = $("#exprBox"); box.textContent = "";
  for (const [n, label] of EXPR) {
    if (!names.has(n)) continue;
    const r = h("input", { type: "range", min: 0, max: 1, step: 0.01, value: weights[n] || 0, "aria-label": label });
    r.addEventListener("input", () => { weights[n] = parseFloat(r.value); viewer.setWeights(weights); });
    box.append(h("label", null, label, r));
  }
  const vis = Array.from(names).filter((n) => n.startsWith("vrc.v_"));
  if (vis.length) {
    const sel = h("select", { "aria-label": "Visema" }, h("option", { value: "" }, "Visema: —"),
      vis.map((v) => h("option", { value: v }, v.replace("vrc.v_", "Visema ").toUpperCase())));
    sel.addEventListener("change", () => {
      for (const v of vis) weights[v] = 0;
      if (sel.value) weights[sel.value] = 1; viewer.setWeights(weights);
    });
    box.append(sel);
  }
}

// ------------------------------------------------------------------ aba Acessórios

const DEFAULT_PART = {
  sphere: { size: [0.08, 0.08, 0.08] }, box: { size: [0.08, 0.08, 0.08] },
  cylinder: { size: [0.06, 0.1, 0.06] }, cone: { size: [0.06, 0.1, 0.06] },
  ring: { size: [0.12, 0.12, 0.012], rot: [90, 0, 0] }, star: { size: [0.08, 0.08, 0.015] },
  heart: { size: [0.08, 0.08, 0.015] }, obj: { size: [0.12, 0.12, 0.12] },
};
const SWATCH = ["#ff5f8f", "#ffd84a", "#4ab0e8", "#7a4bd1", "#2e7d6b", "#f4f1ea", "#e07a3a", "#24262d"];

function shapeLabel(s) { return (META.shapes.find((x) => x[0] === s) || [s, s])[1]; }
function boneLabel(b) { return (META.bones.find((x) => x[0] === b) || [b, b])[1]; }
function getPart(id) { return state.parts.find((p) => p.id === id); }

function addPart(partial, select = true) {
  const shape = partial.shape || "sphere";
  const p = Object.assign({
    id: newId(), name: shapeLabel(shape), group: "Meus acessórios", shape, bone: "Head",
    pos: [0, 0.2, 0], rot: [0, 0, 0], size: [0.08, 0.08, 0.08],
    color: SWATCH[state.parts.length % SWATCH.length], mirror: false, jiggle: false, visible: true, locked: false, preserve_proportions: true,
  }, clone(DEFAULT_PART[shape] || {}), partial);
  state.parts.push(p);
  if (select) selected = p.id;
  renderParts(); schedule(); return p;
}

function renderParts() {
  const list = $("#partList"); list.textContent = "";
  const query = ((document.getElementById("partSearch") || {}).value || "").trim().toLocaleLowerCase("pt-BR");
  const filtered = state.parts.filter((p) => !query || [p.name, p.group, p.shape, p.bone].join(" ").toLocaleLowerCase("pt-BR").includes(query));
  for (const p of filtered) {
    list.append(h("button", { class: "partitem" + (p.id === selected ? " on" : "") + (p.visible === false ? " muted" : ""), onclick: () => { selected = p.id; renderParts(); } },
      h("span", null, (p.locked ? "🔒 " : "") + (p.visible === false ? "◌ " : "") + p.name),
      h("small", null, shapeLabel(p.shape).split(" ")[0] + " · " + p.group)));
  }
  $("#partEmpty").hidden = filtered.length > 0;
  if (!state.parts.length) $("#partEmpty").textContent = "Nenhuma peça ainda. Adicione um modelo da biblioteca ou crie uma forma.";
  else if (!filtered.length) $("#partEmpty").textContent = "Nenhuma peça corresponde à busca.";
  $("#partBadge").textContent = state.parts.length;
  renderEditor();
}

function xyz(label, key, p, step, lo, hi) {
  const row = h("div", { class: "xyz" }, h("span", null, label));
  [0, 1, 2].forEach((i) => {
    const inp = h("input", { type: "number", step, min: lo, max: hi, value: p[key][i], disabled: !!p.locked, "aria-label": label + " " + "XYZ"[i] });
    inp.addEventListener("input", () => {
      const v = parseFloat(inp.value);
      if (Number.isFinite(v)) { p[key][i] = Math.max(lo, Math.min(hi, v)); schedule(); }
    });
    row.append(inp);
  });
  return row;
}

function renderEditor() {
  const box = $("#partEditor"), p = getPart(selected);
  box.hidden = !p; if (!p) return;
  box.textContent = "";
  const text = (label, key, extra) => {
    const inp = h("input", Object.assign({ type: "text", maxlength: 40, value: p[key], disabled: !!p.locked }, extra || {}));
    inp.addEventListener("input", () => { p[key] = inp.value; schedule(); });
    inp.addEventListener("change", renderParts);
    return h("div", { class: "field simple" }, h("label", null, label), inp);
  };
  const groups = Array.from(new Set(state.parts.map((x) => x.group)));
  const dl = h("datalist", { id: "groupList" }, groups.map((g) => h("option", { value: g })));
  const shapeSel = h("select", { disabled: p.shape === "obj" || !!p.locked },
    META.shapes.filter((s) => s[0] !== "obj" || p.shape === "obj").map(([v, l]) => h("option", { value: v }, l)));
  shapeSel.value = p.shape;
  shapeSel.addEventListener("change", () => { p.shape = shapeSel.value; renderParts(); schedule(); });
  const boneSel = h("select", { disabled: !!p.locked }, META.bones.map(([v, l]) => h("option", { value: v }, l)));
  boneSel.value = p.bone;
  boneSel.addEventListener("change", () => { p.bone = boneSel.value; renderParts(); schedule(); });
  const color = h("input", { type: "color", value: p.color, disabled: !!p.locked });
  color.addEventListener("input", () => { p.color = color.value; schedule(); });
  const chk = (label, key, tip) => {
    const c = h("input", { type: "checkbox", id: "pc_" + key, disabled: !!p.locked && key !== "locked" }); c.checked = key === "visible" ? p[key] !== false : !!p[key];
    c.addEventListener("change", () => { p[key] = c.checked; if (key === "locked") renderParts(); schedule(); });
    return h("div", { class: "field check", title: tip }, c, h("label", { for: "pc_" + key }, label));
  };
  const groupInp = text("Grupo (= 1 malha)", "group", { list: "groupList" });
  box.append(h("h3", null, "Editar peça"), dl, text("Nome", "name"), groupInp,
    h("div", { class: "field simple" }, h("label", null, "Forma"), shapeSel),
    h("div", { class: "field simple" }, h("label", null, "Preso ao osso"), boneSel),
    xyz("Posição", "pos", p, 0.005, -3, 3), xyz("Rotação°", "rot", p, 5, -720, 720), xyz("Tamanho", "size", p, 0.005, 0.002, 3),
    h("div", { class: "field simple" }, h("label", null, "Cor"), color),
    chk("Espelhar (cria a cópia do outro lado)", "mirror", "Para ossos _L/_R, usa o osso oposto"),
    chk("Balançar (PhysBone próprio)", "jiggle", "Sininho, capa, antena, cabelo solto..."),
    chk("Mostrar peça na exportação", "visible", "Peças ocultas não entram na malha exportada"),
    ...(p.shape === "obj" ? [chk("Preservar proporções do OBJ", "preserve_proportions", "Mantém a escala uniforme ao redimensionar o modelo")] : []),
    chk("Bloquear edição da peça", "locked", "Desative para editar novamente"),
    h("p", { class: "hint" }, "Posição em metros, relativa ao osso (na cabeça: ao centro dela). +X = lado direito do avatar, +Y = cima, +Z = frente."),
    h("div", { class: "btnrow" },
      h("button", { disabled: !!p.locked, onclick: () => { const c = clone(p); c.id = newId(); c.name += " (cópia)"; c.locked = false; c.pos[0] += 0.02; state.parts.push(c); selected = c.id; renderParts(); schedule(); } }, "Duplicar"),
      h("button", { class: "danger", disabled: !!p.locked, onclick: () => { if (!confirm("Remover a peça '" + p.name + "'?")) return; state.parts = state.parts.filter((x) => x.id !== p.id); selected = state.parts.length ? state.parts[state.parts.length - 1].id : null; renderParts(); schedule(); } }, "Remover")));
}

async function addTemplate() {
  const id = $("#tplSelect").value;
  if (!id) { toast("Nenhum modelo disponível para adicionar."); return; }
  try {
    const r = await API("/api/template", { template: id, spec: state });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "erro");
    let first = null;
    for (const part of data.parts) { const p = addPart(part, false); first = first || p; }
    if (first) selected = first.id;
    renderParts(); schedule();
    toast("Modelo adicionado: " + (META.templates.find((t) => t.id === id) || {}).label);
  } catch (e) { toast("Não foi possível adicionar o modelo: " + e.message, 6000); }
}

function importObj(file) {
  const msg = $("#objMsg");
  if (file.size > 2000000) { msg.textContent = "Arquivo grande demais (máx. 2 MB)."; return; }
  const reader = new FileReader();
  reader.onload = async () => {
    const text = String(reader.result);
    try {
      const r = await API("/api/obj-check", { text });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "falha na análise OBJ");
      if (!data.valid) { msg.textContent = (data.issues || ["OBJ sem geometria válida"]).join(" · "); return; }
      addPart({ shape: "obj", name: file.name.replace(/\.obj$/i, "").slice(0, 30), obj: text });
      const info = data.info;
      const warnings = (data.issues || []).length ? " Avisos: " + data.issues.join(" · ") : "";
      msg.textContent = info.vertices.toLocaleString("pt-BR") + " vértices, " + info.faces.toLocaleString("pt-BR") +
        " faces, " + info.triangles.toLocaleString("pt-BR") + " triângulos." + warnings +
        " MTL/UV/normais de origem não são importados; o Studio usa sua paleta e recalcula normais.";
    } catch (e) { msg.textContent = "Falha ao analisar OBJ: " + e.message; }
  };
  reader.onerror = () => { msg.textContent = "Não foi possível ler o arquivo OBJ."; };
  reader.readAsText(file);
}

function renderTemplateOptions() {
  const select = $("#tplSelect"), q = $("#tplSearch").value.trim().toLocaleLowerCase("pt-BR"), previous = select.value;
  select.textContent = "";
  const matches = META.templates.filter((t) => !q || (t.id + " " + t.label).toLocaleLowerCase("pt-BR").includes(q));
  for (const t of matches) select.append(h("option", { value: t.id }, t.label));
  if (!matches.length) select.append(h("option", { value: "" }, "Nenhum modelo encontrado"));
  if (matches.some((t) => t.id === previous)) select.value = previous;
  $("#tplAdd").disabled = matches.length === 0;
}

function buildParts() {
  renderTemplateOptions();
  $("#tplSearch").addEventListener("input", renderTemplateOptions);
  $("#partSearch").addEventListener("input", renderParts);
  $("#tplAdd").addEventListener("click", addTemplate);
  const sb = $("#shapeButtons");
  for (const [v, l] of META.shapes) {
    if (v === "obj") continue;
    sb.append(h("button", { onclick: () => addPart({ shape: v }) }, "+ " + l.split(" ")[0]));
  }
  $("#objBtn").addEventListener("click", () => $("#objFile").click());
  $("#objFile").addEventListener("change", (e) => { if (e.target.files[0]) importObj(e.target.files[0]); e.target.value = ""; });
}

// ------------------------------------------------------------------ ações do topo

function download(blob, name) {
  const a = h("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

async function doExport() {
  const btn = $("#btnExport"); btn.disabled = true; toast("Gerando o pacote… (pode levar alguns segundos)", 20000);
  try {
    const r = await API("/api/export", { spec: state });
    if (!r.ok) { const e = await r.json(); throw new Error(e.error || "erro"); }
    const blob = await r.blob();
    const name = (state.name || "Avatar").replace(/[^\w\-]/g, "") || "Avatar";
    download(blob, name + ".zip");
    toast("Pronto! Pacote ZIP baixado (inclui manifesto e hashes). Arquivos em " + (r.headers.get("X-Saved-To") || "output/") + ".", 7000);
  } catch (e) { toast("Falha ao exportar: " + e.message, 7000); } finally { btn.disabled = false; }
}

function savePreset() {
  const name = (state.name || "Avatar").replace(/[^\w\-]/g, "") || "Avatar";
  download(new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }), name + ".preset.json");
}

function loadPreset(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(String(reader.result));
      if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("formato inválido");
      state = normalizeState(data); selected = state.parts.length ? state.parts[0].id : null;
      undoStack = []; redoStack = []; historyCurrent = JSON.stringify(state); updateHistoryButtons();
      syncControls(); renderParts(); schedule(false); toast("Preset carregado.");
    } catch (e) { toast("Não consegui abrir o preset: " + e.message, 6000); }
  };
  reader.readAsText(file);
}

async function randomize() {
  try {
    const r = await API("/api/random", { seed: Math.floor(Math.random() * 1e9) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "erro");
    for (const k of ["name", "parts", "merge_meshes", "detail", "fingers", "height"]) delete data[k];
    Object.assign(state, data); syncControls(); schedule();
  } catch (e) { toast("Não foi possível gerar variação: " + e.message, 6000); }
}


// ------------------------------------------------------------------ AI Avatar Workshop (arquivos originais + tarefas Meshy)
let workshopData = { assets: [], tasks: [], ai: { configured: false } };
let workshopPollTimer = null;
let workshopPolling = false;

function aiMode() {
  return $('input[name="aiMode"]:checked')?.value || "preserve";
}

function setAiMode(mode) {
  const value = mode === "personalize" ? "personalize" : "preserve";
  $(value === "preserve" ? "#aiModePreserve" : "#aiModePersonalize").checked = true;
  try { localStorage.setItem("vas.aiMode", value); } catch (e) { /* storage opcional */ }
  const preserve = value === "preserve";
  $("#aiModeNotice").textContent = preserve
    ? "Modo Preservar ativo: o modelo-base, rosto, corpo e esqueleto não serão enviados para operações que os alterem. A IA cria cabelos, roupas e acessórios como arquivos separados."
    : "Modo Personalizar ativo: retexturização e remalhagem serão aplicadas somente a uma cópia derivada do modelo-base. Para remodelar livremente rosto/corpo, ainda será necessário editar a malha em Blender ou outro editor 3D e revisar o rig."
  const kind = $("#aiAssetKind");
  const characterOption = kind.querySelector('option[value="character"]');
  if (characterOption) characterOption.disabled = preserve;
  if (preserve && kind.value === "character") kind.value = "accessory";
}

async function workshopRequest(url, body) {
  const response = await API(url, body);
  let data = {};
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) data = await response.json();
  else data = { error: await response.text() };
  if (!response.ok) throw new Error(data.error || "Falha na operação.");
  return data;
}

function bytesToBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + chunk, bytes.length)));
  }
  return btoa(binary);
}

async function uploadWorkshopFile(file, category) {
  if (file.size > 25 * 1024 * 1024) throw new Error("O arquivo excede 25 MB.");
  const encoded = bytesToBase64(await file.arrayBuffer());
  const data = await workshopRequest("/api/assets/upload", {
    filename: file.name, category, content_base64: encoded,
  });
  return data.asset;
}

function assetOptions(selector, predicate, emptyLabel) {
  const select = $(selector), current = select.value;
  const items = workshopData.assets.filter(predicate);
  select.textContent = "";
  select.append(h("option", { value: "" }, emptyLabel));
  items.forEach((asset) => select.append(h("option", { value: asset.id }, asset.name + " · " + asset.category_label)));
  if (items.some((x) => x.id === current)) select.value = current;
}

function renderWorkshop() {
  assetOptions("#baseModelSelect", (a) => a.category === "base_model", "Nenhum modelo enviado");
  assetOptions("#targetAssetSelect", (a) => ["base_model", "accessory", "generated"].includes(a.category), "Nenhum modelo enviado");
  assetOptions("#referenceAssetSelect", (a) => ["reference", "texture"].includes(a.category), "Nenhuma imagem");
  const list = $("#workAssetList"); list.textContent = "";
  if (!workshopData.assets.length) {
    list.append(h("p", { class: "hint" }, "Nenhum arquivo enviado ainda."));
  } else {
    workshopData.assets.forEach((asset) => {
      const size = (asset.size / (1024 * 1024)).toFixed(2).replace(".", ",") + " MB";
      const info = h("div", { class: "asset-info" },
        h("b", null, asset.name),
        h("small", null, asset.category_label + " · " + size + " · SHA-256 " + asset.sha256.slice(0, 12) + "…"));
      const controls = h("div", { class: "asset-actions" });
      if (asset.category === "base_model") {
        controls.append(h("button", { onclick: () => { $("#baseModelSelect").value = asset.id; $("#targetAssetSelect").value = asset.id; toast("Modelo-base selecionado."); } }, "Usar como base"));
      }
      controls.append(h("a", { href: "/api/assets/download/" + asset.id, class: "text-link" }, "Baixar"));
      list.append(h("div", { class: "asset-row" }, info, controls));
    });
  }
  renderWorkshopTasks();
  updateMeshyStatus();
  setAiMode(aiMode());
}

function updateMeshyStatus() {
  const status = $("#meshyStatus");
  const configured = !!workshopData.ai.configured;
  status.textContent = configured
    ? "Conectado à API Meshy. A chave permanece somente na memória do servidor local."
    : "IA desconectada. Cole sua chave Meshy para habilitar a geração.";
  status.classList.toggle("ok-text", configured);
}

function renderWorkshopTasks() {
  const root = $("#aiTasks"); root.textContent = "";
  const jobs = workshopData.tasks || [];
  if (!jobs.length) { root.append(h("p", { class: "hint" }, "Suas tarefas de IA aparecerão aqui.")); return; }
  jobs.forEach((job) => {
    const terminal = ["SUCCEEDED", "FAILED", "CANCELED"].includes(job.status);
    const status = job.status === "SUCCEEDED" ? "Concluído" : job.status === "FAILED" ? "Falhou" : job.status === "CANCELED" ? "Cancelado" : "Processando";
    const header = h("div", { class: "task-header" },
      h("b", null, (job.asset_kind || "modelo") + " · " + (job.operation || "geração").replaceAll("_", " ")),
      h("span", { class: "task-status " + (job.status === "SUCCEEDED" ? "success" : job.status === "FAILED" ? "failed" : "") }, status));
    const progress = h("div", { class: "task-progress" }, h("i", { style: "width:" + (job.progress || 0) + "%" }));
    const desc = h("p", { class: "hint" }, job.note || job.prompt || "");
    const card = h("div", { class: "task-card" }, header, progress, h("small", null, (job.progress || 0) + "% · " + new Date((job.created_at || 0) * 1000).toLocaleString("pt-BR")), desc);
    if (job.error || job.download_error) card.append(h("p", { class: "error-text" }, job.error || job.download_error));
    if (job.result_asset_id) {
      card.append(h("a", { class: "text-link", href: "/api/assets/download/" + job.result_asset_id }, "Baixar modelo GLB gerado"));
    }
    if (job.route === "text_to_3d" && job.operation === "text_to_3d" && job.status === "SUCCEEDED") {
      const refine = h("button", { onclick: () => refineWorkshopTask(job.id) }, "Gerar texturas PBR (refinar)");
      card.append(refine);
    }
    if (!terminal) card.classList.add("task-running");
    root.append(card);
  });
}

async function refreshWorkshop(poll = true) {
  try {
    const response = await fetch("/api/workshop", { cache: "no-store" });
    if (!response.ok) throw new Error("Não foi possível acessar a biblioteca local.");
    workshopData = await response.json();
    renderWorkshop();
    if (poll && workshopData.ai.configured && workshopData.tasks.some((j) => !["SUCCEEDED", "FAILED", "CANCELED"].includes(j.status))) {
      if (workshopPollTimer) clearTimeout(workshopPollTimer);
      workshopPollTimer = setTimeout(pollWorkshopTasks, 7000);
    }
  } catch (e) { $("#aiActionMsg").textContent = e.message; }
}

async function pollWorkshopTasks() {
  if (workshopPolling) return;
  workshopPolling = true;
  try {
    const pendingJobs = workshopData.tasks.filter((j) => !["SUCCEEDED", "FAILED", "CANCELED"].includes(j.status)).slice(0, 4);
    for (const job of pendingJobs) {
      try {
        const response = await fetch("/api/ai/tasks/" + job.id, { cache: "no-store" });
        const data = await response.json();
        if (response.ok) Object.assign(job, data);
        else if (data.error) job.error = data.error;
      } catch (e) { /* nova tentativa no próximo ciclo */ }
    }
    renderWorkshopTasks();
  } finally {
    workshopPolling = false;
    if (workshopData.ai.configured && workshopData.tasks.some((j) => !["SUCCEEDED", "FAILED", "CANCELED"].includes(j.status))) {
      workshopPollTimer = setTimeout(pollWorkshopTasks, 7000);
    } else {
      await refreshWorkshop(false);
    }
  }
}

async function connectMeshy() {
  const button = $("#btnMeshyKey"); button.disabled = true;
  try {
    const data = await workshopRequest("/api/ai/config", { api_key: $("#meshyKey").value.trim() });
    $("#meshyKey").value = "";
    workshopData.ai = { provider: "Meshy", configured: data.configured };
    updateMeshyStatus();
    toast(data.configured ? "API Meshy conectada nesta execução." : "Chave removida da memória do servidor.");
    if (data.configured) await refreshWorkshop();
  } catch (e) { toast(e.message, 6000); }
  finally { button.disabled = false; }
}

async function uploadBaseModel(file) {
  const msg = $("#aiActionMsg"); msg.textContent = "Enviando e verificando o modelo-base…";
  try {
    const asset = await uploadWorkshopFile(file, "base_model");
    await refreshWorkshop(false);
    $("#baseModelSelect").value = asset.id; $("#targetAssetSelect").value = asset.id;
    msg.textContent = "Modelo-base salvo como original imutável. SHA-256: " + asset.sha256;
  } catch (e) { msg.textContent = "Falha no upload: " + e.message; }
}

async function uploadWorkFiles(files) {
  const msg = $("#aiActionMsg");
  for (const file of files) {
    const ext = file.name.split(".").pop().toLowerCase();
    const category = ["png", "jpg", "jpeg", "webp"].includes(ext)
      ? $("#workAssetCategory").value === "texture" ? "texture" : "reference"
      : "accessory";
    try {
      msg.textContent = "Enviando " + file.name + "…";
      await uploadWorkshopFile(file, category);
    } catch (e) { toast(file.name + ": " + e.message, 6500); }
  }
  await refreshWorkshop(false);
  msg.textContent = "Upload concluído. Os arquivos originais foram preservados na biblioteca local.";
}

async function createWorkshopTask(operation) {
  const mode = aiMode();
  const prompt = $("#aiPrompt").value.trim();
  const assetKind = $("#aiAssetKind").value;
  const baseId = $("#baseModelSelect").value;
  const referenceId = $("#referenceAssetSelect").value;
  const targetId = $("#targetAssetSelect").value || baseId;
  if (!workshopData.ai.configured) { toast("Conecte primeiro a API Meshy.", 5000); return; }
  if ((operation === "text_to_3d" || operation === "retexture_base") && !prompt) { toast("Descreva o que deseja."); return; }
  if (operation === "image_to_3d" && !referenceId) { toast("Envie e selecione uma imagem de referência."); return; }
  if ((operation === "retexture_base" || operation === "remesh_base") && !targetId) {
    toast("Selecione um modelo 3D para processar."); return;
  }
  if (mode === "preserve" && assetKind === "character") { toast("No modo Preservar, gere peças separadas; o personagem-base não será substituído."); return; }
  const labels = { text_to_3d: "Gerar uma peça 3D pela descrição", image_to_3d: "Gerar uma peça 3D pela imagem",
    retexture_base: "Criar uma cópia retexturizada do modelo-base", remesh_base: "Criar uma cópia com nova topologia" };
  const confirmText = labels[operation] + ". Esta operação pode consumir créditos da sua conta Meshy. Continuar?";
  if (!window.confirm(confirmText)) return;
  const buttons = ["#btnAiText", "#btnAiImage", "#btnAiRetexture", "#btnAiRemesh"].map((id) => $(id));
  buttons.forEach((b) => { if (b) b.disabled = true; });
  const msg = $("#aiActionMsg"); msg.textContent = "Enviando tarefa à Meshy…";
  try {
    const body = { mode, operation, prompt, asset_kind: assetKind };
    if (baseId) body.base_asset_id = baseId;
    if (referenceId) body.reference_asset_id = referenceId;
    if (operation === "retexture_base" || operation === "remesh_base") {
      body.target_asset_id = targetId;
    } else if (targetId) {
      body.target_asset_id = targetId;
    }
    const job = await workshopRequest("/api/ai/tasks", body);
    msg.textContent = "Tarefa criada. O modelo original continuará intacto; acompanhe o progresso em Tarefas e resultados.";
    await refreshWorkshop(false);
    if (workshopPollTimer) clearTimeout(workshopPollTimer);
    workshopPollTimer = setTimeout(pollWorkshopTasks, 3000);
  } catch (e) { msg.textContent = "Não foi possível iniciar: " + e.message; }
  finally { buttons.forEach((b) => { if (b) b.disabled = false; }); }
}

async function refineWorkshopTask(previewJobId) {
  if (!window.confirm("Gerar texturas PBR para esta prévia? A tarefa pode consumir créditos Meshy.")) return;
  try {
    await workshopRequest("/api/ai/refine", { preview_job_id: previewJobId });
    await refreshWorkshop(false);
    workshopPollTimer = setTimeout(pollWorkshopTasks, 3000);
    toast("Refinamento de texturas iniciado.");
  } catch (e) { toast(e.message, 6500); }
}

function buildAIWorkshop() {
  let savedMode = "preserve";
  try { savedMode = localStorage.getItem("vas.aiMode") || "preserve"; } catch (e) { /* storage opcional */ }
  setAiMode(savedMode);
  ["#aiModePreserve", "#aiModePersonalize"].forEach((id) => $(id).addEventListener("change", () => setAiMode(aiMode())));
  $("#baseModelFile").addEventListener("change", (e) => {
    const file = e.target.files[0]; if (file) uploadBaseModel(file); e.target.value = "";
  });
  $("#workAssetFile").addEventListener("change", (e) => {
    const files = Array.from(e.target.files || []); if (files.length) uploadWorkFiles(files); e.target.value = "";
  });
  $("#btnMeshyKey").addEventListener("click", connectMeshy);
  $("#btnAiText").addEventListener("click", () => createWorkshopTask("text_to_3d"));
  $("#btnAiImage").addEventListener("click", () => createWorkshopTask("image_to_3d"));
  $("#btnAiRetexture").addEventListener("click", () => createWorkshopTask("retexture_base"));
  $("#btnAiRemesh").addEventListener("click", () => createWorkshopTask("remesh_base"));
  refreshWorkshop();
}


// ------------------------------------------------------------------ início

function setTheme(theme) {
  const value = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = value;
  try { localStorage.setItem("vas.theme", value); } catch (e) { /* ignora */ }
  $("#btnTheme").textContent = value === "dark" ? "☀ Tema claro" : "☾ Tema escuro";
  if (viewer) viewer.dirty = true;
}

async function init() {
  META = await (await fetch("/api/schema")).json();
  try { setTheme(localStorage.getItem("vas.theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")); }
  catch (e) { setTheme("light"); }
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("vas.state") || "null"); } catch (e) { saved = null; }
  state = normalizeState(saved);
  historyCurrent = JSON.stringify(state); undoStack = []; redoStack = []; updateHistoryButtons();
  buildLook(); buildParts(); syncControls(); renderPalettes();
  selected = state.parts.length ? state.parts[0].id : null; renderParts();
  $$('[data-style]').forEach((b) => b.addEventListener("click", () => applyStyle(b.dataset.style)));
  $("#paletteSave").addEventListener("click", savePalette);
  $("#paletteApply").addEventListener("click", applyPalette);
  try { viewer = new Viewer($("#gl")); }
  catch (e) {
    $("#gl").hidden = true;
    $(".stage").append(h("div", { class: "viewer-error", role: "alert" },
      "Pré-visualização 3D indisponível: " + e.message + " Atualize o navegador ou habilite WebGL. O editor e a exportação continuam disponíveis."));
    viewer = { meshes: [], setModel() {}, setHidden() {}, setWeights() {}, view() {}, focusHead() {}, resetCamera() {}, setBones() {} };
  }

  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.toggle("on", x === t));
    $$(".pane").forEach((p) => p.classList.toggle("on", p.id === "tab-" + t.dataset.tab));
  }));
  buildAIWorkshop();
  $$("[data-view]").forEach((b) => b.addEventListener("click", () => viewer.view(b.dataset.view)));
  $("#btnResetCamera").addEventListener("click", () => viewer.resetCamera());
  $("#btnHead").addEventListener("click", (e) => {
    const on = e.currentTarget.getAttribute("aria-pressed") !== "true";
    e.currentTarget.setAttribute("aria-pressed", String(on)); viewer.focusHead(on);
  });
  $("#chkBones").addEventListener("change", (e) => viewer.setBones(e.target.checked));
  $("#btnExport").addEventListener("click", doExport);
  $("#btnSave").addEventListener("click", savePreset);
  $("#btnLoad").addEventListener("click", () => $("#fileLoad").click());
  $("#fileLoad").addEventListener("change", (e) => { if (e.target.files[0]) loadPreset(e.target.files[0]); e.target.value = ""; });
  $("#btnRandom").addEventListener("click", randomize);
  $("#btnUndo").addEventListener("click", undo);
  $("#btnRedo").addEventListener("click", redo);
  $("#btnTheme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  window.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const key = e.key.toLowerCase();
    if (key === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
    else if (key === "y" || (key === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
    else if (key === "s") { e.preventDefault(); savePreset(); }
    else if (key === "e") { e.preventDefault(); doExport(); }
  });
  refresh();
}

init().catch((e) => { document.body.prepend(h("p", { style: "padding:16px" }, "Erro ao iniciar: " + e.message)); });
