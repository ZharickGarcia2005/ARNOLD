const users = {
  validator: { name: "José Validador", initials: "JV", label: "Validador" },
  supervisor: { name: "María Supervisora", initials: "MS", label: "Jefe de área" },
  auditor: { name: "Ana Auditoría", initials: "AA", label: "Auditor" },
  admin: { name: "Carlos Administrador", initials: "CA", label: "Administrador" }
};

const shell = document.querySelector(".app-shell");
const session = {
  authenticated: shell?.dataset.authenticated === "true",
  canImport: shell?.dataset.canImport === "true",
  name: shell?.dataset.userName || "",
  role: shell?.dataset.userRole || "validator"
};
const maxUploadBytes = Number(document.getElementById("importModal")?.dataset.maxUploadBytes || 0);
let realBatch = null;
let realPage = 1;
let realSummary = null;
let pollGeneration = 0;
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
})[character]);

const records = [
  { id: 1, status: "critical", title: "EXP-DEMO-001", identity: "17••••••01", contributor: "Contribuyente de prueba A", ciu: "CIU-10421", account: "CTA-55031", amount: 486.35, order: "096", issue: "Conflicto de identidad" },
  { id: 2, status: "duplicate", title: "EXP-DEMO-002", identity: "09••••••42", contributor: "Contribuyente de prueba B", ciu: "CIU-22108", account: "CTA-71780", amount: 932.18, order: "096", issue: "Posible repetido" },
  { id: 3, status: "payment", title: "EXP-DEMO-003", identity: "13••••••19", contributor: "Contribuyente de prueba C", ciu: "CIU-30551", account: "CTA-90017", amount: 214.90, order: "096", issue: "Posible cancelación" },
  { id: 4, status: "ready", title: "EXP-DEMO-004", identity: "17••••••65", contributor: "Contribuyente de prueba D", ciu: "CIU-41076", account: "CTA-03129", amount: 721.04, order: "096", issue: "Sin alertas" },
  { id: 5, status: "critical", title: "EXP-DEMO-005", identity: "09••••••07", contributor: "Contribuyente de prueba E", ciu: "CIU-55911", account: "CTA-77325", amount: 1106.50, order: "096", issue: "Monto incompatible" },
  { id: 6, status: "duplicate", title: "EXP-DEMO-006", identity: "17••••••88", contributor: "Contribuyente de prueba F", ciu: "CIU-62030", account: "CTA-04281", amount: 368.21, order: "096", issue: "Reaparece en otra orden" },
  { id: 7, status: "ready", title: "EXP-DEMO-007", identity: "13••••••70", contributor: "Contribuyente de prueba G", ciu: "CIU-78831", account: "CTA-62309", amount: 590.00, order: "096", issue: "Sin alertas" },
  { id: 8, status: "payment", title: "EXP-DEMO-008", identity: "09••••••31", contributor: "Contribuyente de prueba H", ciu: "CIU-88920", account: "CTA-80146", amount: 143.77, order: "096", issue: "Pago histórico encontrado" }
];

let state = {
  role: session.authenticated && users[session.role] ? session.role : "validator", view: "dashboard", filter: "all", search: "", editingId: null,
  approvals: [
    { id: 101, recordId: 5, requester: "José Validador", field: "Valor total", oldValue: "$ 1.106,50", newValue: "$ 986,50", reason: "Valor confirmado con respaldo de la entidad", status: "pending" }
  ],
  audit: [
    { icon: "⇧", title: "Base de demostración cargada", detail: "8 registros · lote PRE-096", user: "Sistema", time: "Hoy · 08:42" },
    { icon: "!", title: "Reglas automáticas ejecutadas", detail: "6 alertas detectadas y 2 registros sin observaciones", user: "ARNOLD", time: "Hoy · 08:43" },
    { icon: "→", title: "Corrección enviada a aprobación", detail: "Cambio solicitado en un campo monetario protegido", user: "José Validador", time: "Hoy · 09:05" }
  ]
};

const protectedFields = new Set(["title", "identity", "amount"]);
const pageTitles = { dashboard: "Resumen de validación", preliminar: "Base preliminar", sources: "Fuentes y reglas", approvals: "Aprobaciones", audit: "Bitácora de actividad", security: "Seguridad y permisos" };
const money = value => new Intl.NumberFormat("es-EC", { style: "currency", currency: "USD" }).format(value);

function permissions() {
  const role = state.role;
  return {
    canEdit: !realBatch && (role === "validator" || role === "supervisor" || role === "admin"),
    canApprove: role === "supervisor" || role === "admin",
    canImport: session.authenticated && session.canImport,
    directSensitiveEdit: role === "supervisor" || role === "admin"
  };
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".view").forEach(el => el.classList.remove("active"));
  document.getElementById(`${view}View`).classList.add("active");
  document.querySelectorAll(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.view === view));
  document.getElementById("pageTitle").textContent = pageTitles[view];
  if (view === "approvals") renderApprovals();
  if (view === "audit") renderAudit();
  if (view === "sources") renderSources();
}

function renderAll() {
  const user = session.authenticated
    ? { ...users[state.role], name: session.name || users[state.role].name }
    : users[state.role];
  document.getElementById("userName").textContent = user.name;
  document.getElementById("userRole").textContent = user.label;
  document.getElementById("avatar").textContent = user.initials;
  document.getElementById("roleSelect").value = state.role;
  document.querySelectorAll(".can-import").forEach(btn => btn.disabled = !permissions().canImport);
  const critical = records.filter(r => r.status === "critical").length;
  const duplicate = records.filter(r => r.status === "duplicate").length;
  const ready = records.filter(r => r.status === "ready").length;
  document.getElementById("metricTotal").textContent = records.length.toLocaleString("es-EC");
  document.getElementById("metricCritical").textContent = critical;
  document.getElementById("metricDuplicates").textContent = duplicate;
  document.getElementById("metricReady").textContent = ready;
  document.getElementById("issueCount").textContent = records.filter(r => r.status !== "ready").length;
  document.getElementById("approvalCount").textContent = state.approvals.filter(a => a.status === "pending").length;
  renderQuality(); renderRecords(); renderApprovals(); renderAudit(); renderPermissionNote(); renderSources();
  if (realBatch) {
    document.getElementById("metricTotal").textContent = realSummary?.total ?? 0;
    document.getElementById("metricCritical").textContent = realSummary?.critical_count ?? 0;
    document.getElementById("metricDuplicates").textContent = realSummary?.duplicate_count ?? 0;
    document.getElementById("metricReady").textContent = realSummary?.counts?.ready ?? 0;
    document.getElementById("issueCount").textContent = realSummary?.issue_count ?? 0;
    document.querySelector(".hero-card .status-pill").textContent = realBatch.name;
    document.querySelector(".metric-card em").textContent = "Cartera seleccionada";
    document.getElementById("permissionNote").textContent = "Datos reales en consulta. Las correcciones y aprobaciones se conectarán en la siguiente fase. Búsqueda y filtros se aplican a la página actual.";
    document.getElementById("exportBtn").disabled = true;
    document.getElementById("tableMode").textContent = "Fila original del Excel · consulta sin modificar el archivo";
    document.getElementById("qualityBars").textContent = `${realSummary?.total ?? 0} filas procesadas · ${realSummary?.issue_count ?? 0} incidencias. Los conteos críticos y repetidos representan incidencias, no personas únicas.`;
  }
}

function renderSources() {
  const catalog = window.ARNOLD_SOURCE_CATALOG;
  if (!catalog) return;
  const nf = new Intl.NumberFormat("es-EC");
  const monthly = catalog.sources.filter(s => s.id === "julio-2026" || s.id === "agosto-2026");
  const totalMonthlyRows = monthly.reduce((sum, source) => sum + source.rawRows, 0);
  const totalResults = monthly.reduce((sum, source) => sum + source.resultRows, 0);
  const criticalRules = catalog.rules.filter(rule => rule.severity === "critical").length;
  document.getElementById("configVersion").textContent = `Reglas ${catalog.version}`;
  document.getElementById("ruleCount").textContent = `${catalog.rules.length} reglas`;
  document.getElementById("sourceSummary").innerHTML = `
    <article><small>Fuentes perfiladas</small><strong>${catalog.sources.length}</strong><span>XLSX y XLS</span></article>
    <article><small>Filas mensuales analizadas</small><strong>${nf.format(totalMonthlyRows)}</strong><span>Julio + agosto</span></article>
    <article><small>Filas consolidadas</small><strong>${nf.format(totalResults)}</strong><span>Sin contar copias</span></article>
    <article><small>Controles críticos</small><strong>${criticalRules}</strong><span>Bloquean el cierre</span></article>`;
  document.getElementById("sourceCards").innerHTML = catalog.sources.map(source => `
    <article class="source-card ${source.status}">
      <div class="source-card-head"><span class="file-kind">${source.format}</span><span class="source-status">${source.status === "recognized" ? "Reconocida" : source.status === "duplicate" ? "Copia detectada" : "Con alertas"}</span></div>
      <h3>${source.label}</h3>
      <div class="source-numbers"><span><b>${nf.format(source.rawRows)}</b> filas fuente</span><span><b>${nf.format(source.resultRows)}</b> filas resultado</span></div>
      <ul>${source.notes.map(note => `<li>${note}</li>`).join("")}</ul>
    </article>`).join("");
  document.getElementById("ruleList").innerHTML = catalog.rules.map(rule => `
    <div class="rule-item"><span class="rule-severity ${rule.severity}">${rule.severity === "critical" ? "Crítica" : rule.severity === "warning" ? "Alerta" : "Control"}</span><div><strong>${rule.id} · ${rule.title}</strong><p>${rule.description}</p></div></div>`).join("");
}

function renderQuality() {
  const groups = [
    ["Problemas críticos", "critical", "red"], ["Posibles repetidos", "duplicate", "amber"],
    ["Pago o cancelación", "payment", "blue"], ["Sin observaciones", "ready", "green"]
  ];
  document.getElementById("qualityBars").innerHTML = groups.map(([label, status, color]) => {
    const count = records.filter(r => r.status === status).length;
    const pct = records.length ? Math.round((count / records.length) * 100) : 0;
    return `<div class="quality-row"><label>${label}</label><div class="bar"><i class="${color}" style="width:${pct}%"></i></div><b>${count}</b></div>`;
  }).join("");
}

function filteredRecords() {
  const q = state.search.toUpperCase();
  return records.filter(r => (state.filter === "all" || r.status === state.filter) && (!q || [r.title, r.identity, r.contributor, r.ciu, r.account].some(v => v.toUpperCase().includes(q))));
}

function renderRecords() {
  const visible = filteredRecords();
  document.getElementById("visibleRows").textContent = `${visible.length} registros`;
  const p = permissions();
  document.getElementById("recordsBody").innerHTML = visible.map(r => `<tr>
    <td><span class="issue-tag ${escapeHtml(r.status)}">${escapeHtml(r.issue)}</span></td>
    <td class="record-title">${escapeHtml(r.title)}</td><td>${escapeHtml(r.identity)}</td><td>${escapeHtml(r.contributor)}</td>
    <td>${escapeHtml(r.ciu)}</td><td>${escapeHtml(r.account)}</td><td class="numeric">${r.amount == null ? "Sin importe válido" : money(r.amount)}</td><td>${escapeHtml(r.order)}</td>
    <td><button class="row-action" data-edit="${escapeHtml(r.id)}" ${p.canEdit ? "" : "disabled"}>Editar</button></td>
  </tr>`).join("") || `<tr><td colspan="9"><div class="empty-state"><strong>Sin coincidencias</strong>Prueba con otro filtro o búsqueda.</div></td></tr>`;
  document.querySelectorAll("[data-edit]").forEach(btn => btn.addEventListener("click", () => openEdit(Number(btn.dataset.edit))));
}

function renderPermissionNote() {
  const text = {
    validator: "Como validador puedes corregir datos comunes. Los cambios de título, identificación o monto se enviarán al jefe de área.",
    supervisor: "Como jefe de área puedes editar campos sensibles, resolver solicitudes y aprobar el lote.",
    auditor: "Modo de consulta: puedes revisar registros y bitácora, pero no modificar información.",
    admin: "Como administrador tienes acceso completo, incluida la gestión de usuarios y permisos."
  };
  document.getElementById("permissionNote").textContent = text[state.role];
}

function renderApprovals() {
  const list = document.getElementById("approvalList");
  const pending = state.approvals.filter(a => a.status === "pending");
  if (!pending.length) { list.innerHTML = `<div class="empty-state"><strong>No hay solicitudes pendientes</strong>Las nuevas solicitudes aparecerán aquí.</div>`; return; }
  list.innerHTML = pending.map(a => `<article class="approval-card"><div><span class="issue-tag duplicate">Cambio protegido</span><h4>${escapeHtml(a.field)}: ${escapeHtml(a.oldValue)} → ${escapeHtml(a.newValue)}</h4><p>${escapeHtml(a.reason)} · solicitado por ${escapeHtml(a.requester)}</p></div><div class="approval-actions"><button class="btn reject" data-reject="${Number(a.id)}" ${permissions().canApprove ? "" : "disabled"}>Rechazar</button><button class="btn approve" data-approve="${Number(a.id)}" ${permissions().canApprove ? "" : "disabled"}>Aprobar</button></div></article>`).join("");
  list.querySelectorAll("[data-approve]").forEach(b => b.onclick = () => decideApproval(Number(b.dataset.approve), true));
  list.querySelectorAll("[data-reject]").forEach(b => b.onclick = () => decideApproval(Number(b.dataset.reject), false));
}

function renderAudit() {
  document.getElementById("auditList").innerHTML = state.audit.map(a => `<div class="audit-item"><span class="audit-icon">${escapeHtml(a.icon)}</span><div><strong>${escapeHtml(a.title)}</strong><p>${escapeHtml(a.detail)}</p><span class="muted">${escapeHtml(a.user)}</span></div><time class="audit-time">${escapeHtml(a.time)}</time></div>`).join("");
}

function openEdit(id) {
  if (!permissions().canEdit) return showToast("Tu rol permite únicamente consultar.");
  state.editingId = id;
  const r = records.find(x => x.id === id);
  document.getElementById("editValue").value = r.contributor;
  document.getElementById("editReason").value = "";
  document.getElementById("editField").value = "contributor";
  updateSensitiveWarning(); openModal("editModal");
}

function updateSensitiveWarning() {
  const sensitive = protectedFields.has(document.getElementById("editField").value);
  const warning = document.getElementById("sensitiveWarning");
  if (sensitive && !permissions().directSensitiveEdit) {
    warning.textContent = "Este campo está protegido. El cambio se guardará como solicitud pendiente y no alterará el registro hasta que un jefe lo apruebe.";
    warning.classList.add("show");
    document.getElementById("saveEditBtn").textContent = "Enviar a aprobación";
  } else {
    warning.classList.remove("show");
    document.getElementById("saveEditBtn").textContent = "Guardar cambio";
  }
}

function saveEdit() {
  const field = document.getElementById("editField").value;
  const value = document.getElementById("editValue").value.trim();
  const reason = document.getElementById("editReason").value.trim();
  if (!value || !reason) return showToast("Completa el nuevo valor y el motivo.");
  const record = records.find(r => r.id === state.editingId);
  const labels = { contributor: "Contribuyente", account: "Cuenta de agua", title: "Título / expediente", identity: "Identificación", amount: "Valor total" };
  const oldValue = field === "amount" ? money(record[field]) : record[field];
  const newValue = field === "amount" ? money(Number(value.replace(",", ".")) || 0) : value;
  if (protectedFields.has(field) && !permissions().directSensitiveEdit) {
    state.approvals.push({ id: Date.now(), recordId: record.id, requester: users[state.role].name, field: labels[field], oldValue, newValue, rawField: field, rawValue: value, reason, status: "pending" });
    state.audit.unshift({ icon: "→", title: "Cambio enviado a aprobación", detail: `${labels[field]} protegido · ${reason}`, user: users[state.role].name, time: "Ahora" });
    showToast("Solicitud enviada al jefe de área.");
  } else {
    record[field] = field === "amount" ? Number(value.replace(",", ".")) : value;
    state.audit.unshift({ icon: "✎", title: "Registro corregido", detail: `${labels[field]} actualizado · ${reason}`, user: users[state.role].name, time: "Ahora" });
    showToast("Cambio guardado y registrado en bitácora.");
  }
  closeModal("editModal"); renderAll();
}

function decideApproval(id, approved) {
  if (!permissions().canApprove) return showToast("Solo un jefe o administrador puede decidir.");
  const request = state.approvals.find(a => a.id === id);
  request.status = approved ? "approved" : "rejected";
  if (approved && request.rawField) {
    const record = records.find(r => r.id === request.recordId);
    record[request.rawField] = request.rawField === "amount" ? Number(request.rawValue.replace(",", ".")) : request.rawValue;
  }
  state.audit.unshift({ icon: approved ? "✓" : "×", title: approved ? "Cambio aprobado" : "Cambio rechazado", detail: `${request.field} · ${request.reason}`, user: users[state.role].name, time: "Ahora" });
  showToast(approved ? "Solicitud aprobada." : "Solicitud rechazada."); renderAll();
}

function openModal(id) { const m = document.getElementById(id); m.classList.add("open"); m.setAttribute("aria-hidden", "false"); }
function closeModal(id) { const m = document.getElementById(id); m.classList.remove("open"); m.setAttribute("aria-hidden", "true"); }
function showToast(message) { const t = document.getElementById("toast"); t.textContent = message; t.classList.add("show"); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => t.classList.remove("show"), 2600); }

function downloadText(filename, content, type = "text/csv") {
  const blob = new Blob([content], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
}

document.querySelectorAll(".nav-item").forEach(btn => btn.addEventListener("click", () => setView(btn.dataset.view)));
document.querySelectorAll("[data-go]").forEach(btn => btn.addEventListener("click", () => setView(btn.dataset.go)));
document.querySelectorAll("[data-close]").forEach(btn => btn.addEventListener("click", () => closeModal(btn.dataset.close)));
document.querySelectorAll(".modal-backdrop").forEach(m => m.addEventListener("click", e => { if (e.target === m) closeModal(m.id); }));
document.getElementById("roleSelect").addEventListener("change", e => { state.role = e.target.value; renderAll(); showToast(`Vista cambiada a ${users[state.role].label}.`); });
document.getElementById("filters").addEventListener("click", e => { if (!e.target.dataset.filter) return; state.filter = e.target.dataset.filter; document.querySelectorAll("#filters button").forEach(b => b.classList.toggle("active", b === e.target)); renderRecords(); });
document.getElementById("searchInput").addEventListener("input", e => { state.search = e.target.value; renderRecords(); });
document.getElementById("editField").addEventListener("change", e => { const r = records.find(x => x.id === state.editingId); document.getElementById("editValue").value = r[e.target.value]; updateSensitiveWarning(); });
document.getElementById("saveEditBtn").addEventListener("click", saveEdit);
document.getElementById("openAuditBtn").addEventListener("click", () => setView("audit"));
["importBtn", "importBtnGrid"].forEach(id => document.getElementById(id).addEventListener("click", () => permissions().canImport ? openModal("importModal") : showToast(session.authenticated ? "Tu usuario no tiene permiso para cargar carteras." : "Inicia sesión con un usuario autorizado para cargar carteras.")));
function updateSelectedFile(file) {
  document.getElementById("uploadFeedback").textContent = "";
  const valid = file && file.name.toLowerCase().endsWith(".xlsx") && file.size <= maxUploadBytes;
  document.getElementById("fileReady").textContent = !file ? "" : valid ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : "Elige un XLSX de hasta 50 MB.";
  document.getElementById("validateFileBtn").disabled = !valid;
}
document.getElementById("fileInput").addEventListener("change", e => updateSelectedFile(e.target.files[0]));
document.getElementById("dropZone").addEventListener("dragover", event => event.preventDefault());
document.getElementById("dropZone").addEventListener("drop", event => {
  event.preventDefault();
  const file = event.dataTransfer.files[0];
  if (!file) return;
  document.getElementById("fileInput").files = event.dataTransfer.files;
  updateSelectedFile(file);
});

async function readJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("El servidor devolvió una respuesta inesperada.");
  }
  return response.json();
}

async function pollBatch(url, displayName) {
  const generation = ++pollGeneration;
  try {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const waitMs = Math.min(2000 * (1.12 ** attempt), 15000);
      await new Promise(resolve => setTimeout(resolve, waitMs));
      if (generation !== pollGeneration) return;
      const response = await fetch(url, { headers: { "Accept": "application/json" } });
      const batch = await readJsonResponse(response);
      if (!response.ok) throw new Error(batch.error?.message || "No se pudo consultar el lote.");
      document.getElementById("batchFeedback").textContent = `${displayName}: ${batch.status === "processing" ? "Validando filas; espera sin volver a cargar el archivo." : batch.status}`;
      if (["ready", "review", "failed"].includes(batch.status)) {
        const labels = { ready: "lista para aprobación", review: "requiere revisión", failed: "falló" };
        const errorDetail = batch.status === "failed" && batch.run?.error_message ? ` · ${batch.run.error_message}` : "";
        state.audit.unshift({ icon: batch.status === "failed" ? "!" : "✓", title: `Validación ${labels[batch.status]}`, detail: `${displayName} · ${batch.row_count} filas · ${batch.run?.issue_count ?? 0} incidencias${errorDetail}`, user: "ARNOLD", time: "Ahora" });
        renderAll();
        showToast(`El lote ${labels[batch.status]}.`);
        await refreshRealBatches(batch.batch_id);
        return;
      }
    }
    document.getElementById("batchFeedback").textContent = "La validación continúa. Pulsa Actualizar para consultar su estado.";
  } catch (error) {
    document.getElementById("batchFeedback").textContent = error.message;
    showToast(error.message);
  }
}

document.getElementById("validateFileBtn").addEventListener("click", async event => {
  const button = event.currentTarget;
  const file = document.getElementById("fileInput").files[0];
  const period = document.getElementById("batchPeriod").value;
  const sheetName = document.getElementById("batchSheet").value.trim();
  const feedback = document.getElementById("uploadFeedback");
  if (!file || !period || !sheetName) {
    feedback.textContent = "Completa periodo, hoja exacta y archivo antes de cargar.";
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("source_type", "cartera_mensual");
  form.append("period", period);
  form.append("sheet_name", sheetName);
  form.append("header_row", document.getElementById("batchHeaderRow").value);
  form.append("schema_name", document.getElementById("batchSchema").value);
  form.append("profile_id", document.getElementById("batchProfile").value);
  const referenceBatchId = document.getElementById("referenceBatchId").value.trim();
  if (referenceBatchId) form.append("reference_batch_id", referenceBatchId);
  button.disabled = true;
  button.textContent = "Cargando…";
  feedback.textContent = "Enviando el archivo. No cierres esta ventana ni vuelvas a pulsar el botón.";
  try {
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    const response = await fetch(button.dataset.uploadUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken, "Accept": "application/json" },
      body: form
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      if (payload.existing_batch_id || payload.batch_id) {
        await refreshRealBatches(payload.existing_batch_id || payload.batch_id);
      }
      throw new Error(payload.error?.message || "No se pudo cargar el archivo.");
    }
    feedback.textContent = "Archivo recibido y registrado. La validación se ejecutará en segundo plano.";
    closeModal("importModal");
    state.audit.unshift({ icon: "⇧", title: "Archivo recibido en cuarentena", detail: `${file.name} · lote ${payload.batch_id.slice(0, 8)}`, user: session.name, time: "Ahora" });
    renderAll();
    showToast("Archivo recibido. ARNOLD inició la validación.");
    await refreshRealBatches(payload.batch_id);
  } catch (error) {
    feedback.textContent = `No se completó la carga: ${error.message}`;
    showToast(error.message);
  } finally {
    button.textContent = "Cargar y validar";
    button.disabled = false;
  }
});
document.getElementById("exportBtn").addEventListener("click", () => { const rows = filteredRecords(); const csv = ["Estado,Titulo,Identificacion,Contribuyente,CIU,Cuenta,Valor,Orden", ...rows.map(r => [r.issue,r.title,r.identity,r.contributor,r.ciu,r.account,r.amount,r.order].map(v => `"${String(v).replaceAll('"','""')}"`).join(","))].join("\n"); downloadText("ARNOLD_incidencias_demo.csv", csv); showToast("Incidencias de demostración exportadas."); });
document.getElementById("auditExport").addEventListener("click", () => { const csv = ["Evento,Detalle,Usuario,Fecha", ...state.audit.map(a => [a.title,a.detail,a.user,a.time].map(v => `"${String(v).replaceAll('"','""')}"`).join(","))].join("\n"); downloadText("ARNOLD_bitacora_demo.csv", csv); showToast("Bitácora de demostración descargada."); });

renderAll();

async function refreshRealBatches(selectedId) {
  try {
    const response = await fetch("/api/v1/batches/", { headers: { Accept: "application/json" } });
    const payload = await readJsonResponse(response);
    if (!response.ok) throw new Error(payload.error?.message || "No se pudieron consultar las carteras.");
    const select = document.getElementById("realBatchSelect");
    select.replaceChildren();
    for (const batch of payload.batches) {
      const option = document.createElement("option");
      option.value = batch.id;
      option.textContent = `${batch.name} · ${batch.status_label} · ${batch.row_count} filas`;
      option.dataset.batch = JSON.stringify(batch);
      select.append(option);
    }
    if (!payload.batches.length) {
      document.getElementById("batchFeedback").textContent = "Todavía no hay carteras registradas. La tabla inferior es demostrativa hasta que cargues una.";
      return;
    }
    if (selectedId && payload.batches.some(batch => batch.id === selectedId)) select.value = selectedId;
    await selectRealBatch();
  } catch (error) {
    document.getElementById("batchFeedback").textContent = error.message;
  }
}

async function selectRealBatch(page = 1) {
  const option = document.getElementById("realBatchSelect").selectedOptions[0];
  if (!option) return;
  ++pollGeneration;
  const selected = JSON.parse(option.dataset.batch);
  realBatch = selected;
  realPage = page;
  const response = await fetch(`${selected.records_url}?page=${page}`, { headers: { Accept: "application/json" } });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(payload.error?.message || "No se pudieron leer las filas.");
  if (realBatch.id !== selected.id) return;
  realSummary = payload;
  records.splice(0, records.length, ...payload.records.map(row => ({
    id: row.id, status: row.status === "ready" ? "ready" : "critical",
    title: row.clave, identity: row.identity, contributor: row.name, ciu: row.ciu,
    account: "—", amount: row.amount, order: `Fila ${row.source_row}`,
    issue: row.status === "ready" ? "Sin alertas" : "Requiere revisión"
  })));
  document.getElementById("realPagination").hidden = false;
  document.getElementById("previousRealPage").disabled = page <= 1;
  document.getElementById("nextRealPage").disabled = !payload.has_next;
  document.getElementById("realPageLabel").textContent = `Página ${page} · ${payload.total} filas · 50 por página`;
  const statusResponse = await fetch(selected.status_url);
  const status = await readJsonResponse(statusResponse);
  if (!statusResponse.ok) throw new Error(status.error?.message || "No se pudo consultar el estado.");
  document.getElementById("batchFeedback").textContent = `${selected.name} · ${selected.status_label} · ${payload.total} filas · ${payload.issue_count} incidencias. ${status.run?.error_message || ""}`;
  const retry = document.getElementById("retryRealBatch");
  retry.hidden = !session.canImport || !["queue_unavailable", "temporary_processing_error", "unexpected_processing_error"].includes(status.run?.error_code);
  const list = document.getElementById("realIssues");
  list.replaceChildren();
  for (const issue of payload.issues) {
    const paragraph = document.createElement("p");
    paragraph.textContent = `${issue.rule_code} · ${issue.severity}: ${issue.message}`;
    list.append(paragraph);
  }
  if (Object.keys(payload.skipped_rules).length) {
    const note = document.createElement("p");
    note.textContent = "Controles no ejecutados por falta de fuentes: " + Object.entries(payload.skipped_rules).map(([code, reason]) => `${code}: ${reason}`).join("; ");
    list.append(note);
  }
  renderAll();
  if (["quarantined", "processing", "received"].includes(status.status)) pollBatch(selected.status_url, selected.name);
}

document.getElementById("refreshBatches").onclick = () => refreshRealBatches(realBatch?.id);
document.getElementById("realBatchSelect").onchange = () => selectRealBatch().catch(error => showToast(error.message));
document.getElementById("previousRealPage").onclick = () => selectRealBatch(realPage - 1).catch(error => showToast(error.message));
document.getElementById("nextRealPage").onclick = () => selectRealBatch(realPage + 1).catch(error => showToast(error.message));
document.getElementById("retryRealBatch").onclick = async () => {
  try {
    const response = await fetch(`/api/v1/batches/${realBatch.id}/retry/`, {
      method: "POST", headers: { "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value }
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) throw new Error(payload.error?.message || "No se pudo reintentar.");
    await refreshRealBatches(realBatch.id);
  } catch (error) { document.getElementById("batchFeedback").textContent = error.message; }
};
refreshRealBatches();
