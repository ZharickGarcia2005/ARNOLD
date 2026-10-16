/* Una única fuente de estado para la hoja. No contiene registros de demostración. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let grid = null;
  const undo = new window.ArnoldSheetModel.DraftUndo();
  const labels = {
    CIU: "CIU", CEDULA_RUC: "Cédula / RUC", NOMBRES: "Nombres", CLAVE: "CLAVE / título",
    DIRECCION: "Dirección", PARROQUIA: "Parroquia", TELEF: "Teléfono", CORREO: "Correo",
    TOTAL_EMISION: "Emisión", TOTAL_INTERES: "Interés", TOTAL_COACTIVA: "Coactiva",
    TOTAL_RECARGO: "Recargo", MESES_DEUDA: "Meses deuda", FECHA_VENCIMIENTO: "Vencimiento"
  };
  const monetary = ["TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO"];
  const protectedFields = new Set(["CIU", "CEDULA_RUC", "CLAVE", ...monetary, "MESES_DEUDA"]);
  const state = { batch: null, batches: [], scope: "clean", search: "", page: 1, data: null,
    dirty: new Map(), busy: false, fetching: false, requestId: 0, view: "grid", focusMode: false,
    gridRestore: null, resetGridPosition: false };
  const money = value => new Intl.NumberFormat("es-EC", { style: "currency", currency: "USD" }).format(value);
  const csrf = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const base = () => `/api/v1/worksheets/${state.batch.id}/`;
  const status = (text, kind = "") => { $("globalStatus").textContent = text; $("globalStatus").className = `sheet-status ${kind}`; };

  function setSidebar(collapsed, remember = true) {
    $("sheetApp").classList.toggle("sidebar-collapsed", collapsed);
    $("sheetSidebar").inert = collapsed;
    $("sheetSidebar").setAttribute("aria-hidden", String(collapsed));
    $("sidebarToggle").setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Mostrar menú" : "Ocultar menú";
    $("sidebarToggle").setAttribute("aria-label", label);
    $("sidebarToggle").title = label;
    if (remember) { try { localStorage.setItem("arnold.sidebarCollapsed", String(collapsed)); } catch { /* La preferencia es opcional. */ } }
  }

  function setFocusMode(enabled) {
    state.focusMode = enabled;
    $("sheetApp").classList.toggle("focus-mode", enabled);
    $("focusToggle").setAttribute("aria-pressed", String(enabled));
    $("focusToggle").textContent = enabled ? "↙ Salir de pantalla completa" : "⛶ Pantalla completa";
    $("focusToggle").title = enabled ? "Volver al espacio normal (Esc)" : "Ampliar la hoja; Esc para salir";
    $("sheetMain").scrollTop = 0;
  }

  function gridPosition() {
    const active = document.activeElement;
    const inside = active?.matches("#gridBody .cell-editor");
    return { left: $("gridWrap").scrollLeft, top: $("gridWrap").scrollTop,
      row: inside ? active.closest("tr").dataset.row : null,
      column: inside ? active.dataset.column : null,
      start: inside ? active.selectionStart : null, end: inside ? active.selectionEnd : null };
  }

  function restoreGridPosition(position) {
    if (position.row) {
      const tr = [...$("gridBody").rows].find(row => row.dataset.row === position.row);
      const input = tr?.querySelector(`.cell-editor[data-column="${position.column}"]`);
      if (input) {
        input.focus({ preventScroll: true });
        if (position.start != null) input.setSelectionRange(position.start, position.end);
      }
    }
    $("gridWrap").scrollLeft = position.left;
    $("gridWrap").scrollTop = position.top;
  }

  async function api(url, data, options = {}) {
    const response = await fetch(url, {
      method: data === undefined ? "GET" : "POST", cache: "no-store", signal: AbortSignal.timeout(60000),
      headers: { Accept: "application/json", ...(data === undefined ? {} : { "Content-Type": "application/json", "X-CSRFToken": csrf() }) },
      ...(data === undefined ? {} : { body: JSON.stringify(data) })
    });
    if (response.status === 401 || response.redirected) throw new Error("La sesión terminó. Inicia sesión nuevamente.");
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) throw new Error(`El servidor respondió ${response.status}. Intenta actualizar; tu cartera permanece guardada.`);
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(payload.error?.message || "No se pudo completar la operación.");
      error.code = payload.error?.code; error.payload = payload; throw error;
    }
    return payload;
  }

  function controls() {
    const dirty = state.dirty.size;
    const visualPending = grid?.pending() || false;
    $("saveButton").disabled = state.busy || state.fetching || !state.data?.capabilities.edit;
    $("discardButton").disabled = state.busy || !dirty;
    $("saveBadge").textContent = state.busy ? "Guardando…" : dirty ? `${dirty} filas pendientes` : "Todo guardado";
    $("saveBadge").style.color = dirty ? "#b27020" : "#13734e";
    $("toolbarSaveStatus").textContent = $("saveBadge").textContent;
    $("toolbarSaveStatus").classList.toggle("pending", !!dirty);
    for (const id of ["downloadClean", "downloadProblems"]) $(id).disabled = state.busy || state.fetching || !state.data?.capabilities.export;
    for (const id of ["confirmSave", "confirmSaveDownload", "cancelChanges", "changeReason"]) $(id).disabled = state.busy;
    $("confirmSaveDownload").disabled = state.busy || !state.data?.capabilities.export;
    $("previousPage").disabled = state.busy || state.fetching || !!dirty || visualPending || state.page <= 1;
    $("nextPage").disabled = state.busy || state.fetching || !!dirty || visualPending || !state.data?.has_next;
    $("batchSelect").disabled = state.busy || state.fetching || !!dirty || visualPending || !state.batches.length;
    $("refreshButton").disabled = state.busy || state.fetching || !!dirty || visualPending;
    $("retryButton").disabled = state.busy || state.fetching;
    $("undoDraft").disabled = state.busy || state.fetching || !state.data?.capabilities.edit || !undo.available;
    grid?.updateStatus();
  }

  function canNavigate() {
    if (state.busy || state.fetching) return false;
    if (grid?.pending()) { status("Espera a que termine el guardado del formato o reinténtalo desde Guardar formato.", "error"); return false; }
    if (state.dirty.size) { status("Guarda o descarta los cambios antes de cambiar de conjunto, página o cartera.", "error"); return false; }
    return true;
  }

  async function loadBatches(preferred) {
    if (!canNavigate()) return;
    state.fetching = true; controls();
    status("Consultando carteras guardadas…");
    try {
      const result = await api("/api/v1/batches/");
      state.batches = result.batches;
      const select = $("batchSelect"); select.replaceChildren();
      const reference = $("uploadReference"); reference.replaceChildren(new Option("Sin referencia histórica", ""));
      for (const batch of state.batches) {
        select.add(new Option(`${batch.name} · ${batch.status_label}`, batch.id));
        if (["ready", "approved", "exported"].includes(batch.status)) reference.add(new Option(`${batch.period} · ${batch.name}`, batch.id));
      }
      const wanted = preferred || state.batch?.id || localStorage.getItem("arnold.selectedBatch");
      state.batch = state.batches.find(batch => batch.id === wanted) || state.batches[0] || null;
      if (!state.batch) {
        state.data = null;
        select.add(new Option("No hay carteras cargadas", ""));
        $("gridBody").innerHTML = '<tr><td class="sheet-empty">Carga una cartera para comenzar. No hay datos de demostración.</td></tr>';
        status("No hay carteras registradas para tu área. Usa Cargar cartera.");
      } else {
        select.value = state.batch.id; localStorage.setItem("arnold.selectedBatch", state.batch.id);
        state.page = 1;
      }
    } catch (error) { status(error.message, "error"); }
    finally { state.fetching = false; controls(); }
    if (state.batch) await loadRows();
  }

  function renderSummary() {
    if (!state.data) return;
    const summary = state.data.summary;
    for (const [id, key] of [["totalCount", "total"], ["cleanCount", "clean"], ["problemCount", "problem"], ["cleanTab", "clean"], ["problemTab", "problem"], ["pendingBadge", "pending_approvals"]]) $(id).textContent = summary[key].toLocaleString("es-EC");
    $("duplicateCount").textContent = `${summary.duplicates.toLocaleString("es-EC")} filas con CLAVE repetida`;
    $("revisionLabel").textContent = `Revisión ${summary.revision}`;
    $("pageNumber").textContent = state.page;
    const total = state.data.filtered_total;
    $("pageInfo").textContent = total ? `${(state.page - 1) * 100 + 1}–${Math.min(state.page * 100, total)} de ${total.toLocaleString("es-EC")} filas${state.search ? " · búsqueda exacta" : ""}` : "Sin coincidencias en este conjunto";
    $("skippedRules").replaceChildren();
    for (const [code, reason] of Object.entries(state.data.skipped_rules)) {
      const p = document.createElement("p"); p.textContent = `${code}: ${reason}`; $("skippedRules").append(p);
    }
  }

  function buildHead() {
    const fields = state.data.fields;
    const columns = [{ field: "#", label: "Fila", width: 55 }, { field: "QUALITY", label: "Revisión", width: 130 },
      ...fields.map(field => ({ field, label: labels[field] || field, width: field === "NOMBRES" || field === "DIRECCION" ? 250 : field === "CORREO" ? 210 : 130 })),
      { field: "TOTAL", label: "Monto pendiente", width: 140 }, { field: "ERRORS", label: "Problemas detectados", width: 400 }];
    const tr = document.createElement("tr");
    columns.forEach((column, position) => {
      const th = document.createElement("th"); th.style.width = `${column.width}px`; th.scope = "col";
      const letter = document.createElement("span"); letter.textContent = position ? String.fromCharCode(64 + position) : "";
      const b = document.createElement("b"); b.textContent = column.label; th.append(letter, b); tr.append(th);
    });
    $("gridHead").replaceChildren(tr);
    return columns;
  }

  function valueFor(row, field) { return state.dirty.get(row.id)?.values[field] ?? row.values[field] ?? ""; }
  function locallyInvalid(field, value) {
    if (["NOMBRES", "CIU", "CLAVE", "CEDULA_RUC"].includes(field) && !value.trim()) return true;
    if (monetary.includes(field)) return !/^\d+(\.\d{1,2})?$/.test(value);
    if (field === "CEDULA_RUC") return !/^(\d{10}|\d{13})$/.test(value);
    if (field === "MESES_DEUDA") return !/^\d{1,6}$/.test(value);
    return false;
  }
  function editCell(row, field, value, input, remember = true) {
    if (remember) undo.record([{id: row.id, field, before: valueFor(row, field), after: value}], `${row.id}:${field}`);
    let change = state.dirty.get(row.id) || { id: row.id, version: row.version, values: {} };
    if (value === row.values[field]) delete change.values[field]; else change.values[field] = value;
    if (Object.keys(change.values).length) state.dirty.set(row.id, change); else state.dirty.delete(row.id);
    input?.parentElement.classList.toggle("dirty", Object.hasOwn(change.values, field));
    input?.parentElement.classList.toggle("cell-error", locallyInvalid(field, value));
    if (monetary.includes(field)) {
      const total = monetary.reduce((sum, name) => sum + Number(valueFor(row, name)), 0);
      const output = input?.closest("tr").querySelector("[data-total]");
      if (output) output.textContent = monetary.every(name => !locallyInvalid(name, valueFor(row, name))) ? money(total) : "Revisar importes";
    }
    controls();
  }

  function undoDraft() {
    if (state.busy || state.fetching || !state.data?.capabilities.edit) return;
    const changes = undo.take();
    for (const change of changes) {
      const r = state.data.rows.findIndex(row => row.id === change.id), c = state.data.fields.indexOf(change.field);
      if (r < 0 || c < 0) continue;
      const input = $("gridBody").rows[r].cells[c + 2].querySelector(".cell-editor");
      input.value = change.before; editCell(state.data.rows[r], change.field, change.before, input, false);
    }
    controls();
    status(changes.length ? "Borrador deshecho. Los cambios ya guardados o aprobados no se revierten." : "No hay borradores que deshacer. Los guardados y formatos no se revierten con Ctrl+Z.");
  }

  function renderRows() {
    if (!state.data) return;
    undo.clear();
    let position = state.gridRestore || gridPosition();
    if (!$("gridWrap").inert) state.gridRestore = null;
    if (state.resetGridPosition) position = { ...position, top: 0, row: null };
    state.resetGridPosition = false;
    const columns = buildHead();
    const fragment = document.createDocumentFragment();
    for (const [position, row] of state.data.rows.entries()) {
      const tr = document.createElement("tr"); tr.dataset.row = row.id;
      const number = document.createElement("td"); number.className = "row-number"; number.textContent = row.source_row; tr.append(number);
      const badge = document.createElement("td"); const tag = document.createElement("span");
      tag.className = `quality-badge ${row.quality}`; tag.textContent = row.quality === "clean" ? "Sin observaciones" : "Requiere revisión"; badge.append(tag); tr.append(badge);
      for (const [column, field] of state.data.fields.entries()) {
        const td = document.createElement("td"); const input = document.createElement("textarea");
        input.rows = 1; input.className = "cell-editor"; input.value = valueFor(row, field); input.maxLength = 1000;
        input.autocomplete = "off"; input.spellcheck = false; input.readOnly = !state.data.capabilities.edit;
        input.setAttribute("aria-label", `${labels[field]} · fila ${row.source_row}`);
        input.dataset.position = position; input.dataset.column = column;
        if (monetary.includes(field)) { input.classList.add("numeric"); input.inputMode = "decimal"; }
        const errors = row.errors.filter(error => error.field === field);
        if (errors.length) { td.classList.add("cell-error"); input.title = errors.map(error => error.message).join(" "); }
        else if (protectedFields.has(field) && !state.data.capabilities.protected) input.title = "Este cambio se enviará a un jefe para aprobación.";
        if (state.dirty.get(row.id)?.values[field] !== undefined) td.classList.add("dirty");
        input.addEventListener("input", () => editCell(row, field, input.value, input));
        td.append(input); tr.append(td);
      }
      const total = document.createElement("td"); const amount = document.createElement("span"); amount.dataset.total = "true"; amount.className = "numeric";
      amount.textContent = row.total == null ? "Revisar importes" : money(row.total); total.append(amount); tr.append(total);
      const errors = document.createElement("td"); const text = document.createElement("span");
      text.textContent = row.errors.map(error => error.message).join(" · ") || "—"; text.title = text.textContent; errors.append(text); tr.append(errors);
      fragment.append(tr);
    }
    $("gridBody").replaceChildren(fragment);
    if (!state.data.rows.length) {
      const tr = document.createElement("tr"); const td = document.createElement("td");
      td.colSpan = 18; td.className = "sheet-empty";
      td.textContent = state.scope === "clean" ? "No hay registros limpios para esta selección. Revisa el conjunto Errores y duplicados." : "No hay registros con problemas para esta selección.";
      tr.append(td); $("gridBody").append(tr);
    }
    restoreGridPosition(position);
    grid?.rendered(state.data, columns);
  }

  async function loadRows(quiet = false) {
    if (!state.batch || state.busy || state.fetching || (quiet && state.dirty.size)) return;
    const token = ++state.requestId, url = base();
    state.fetching = true;
    if (!quiet) { status("Cargando filas de la cartera…"); controls(); }
    try {
      const data = await api(`${url}query/`, { page: state.page, scope: state.scope, search: state.search });
      if (token !== state.requestId) return;
      const needsRender = !quiet || !state.data || data.summary.revision !== state.data.summary.revision;
      if (quiet && state.dirty.size) return;
      state.data = data;
      state.page = data.page;
      $("retryButton").hidden = true;
      if (needsRender) { renderSummary(); renderRows(); }
      else grid?.receivePresentation(data.presentation);
      if (!quiet || needsRender) status(`${data.name} · ${data.summary.total.toLocaleString("es-EC")} filas procesadas. ${data.summary.problem.toLocaleString("es-EC")} separadas para revisión.`, "success");
      return true;
    } catch (error) {
      if (token !== state.requestId) return;
      if (error.code === "preparing") {
        state.data = null;
        const batchStatus = await api(state.batch.status_url).catch(() => null);
        $("retryButton").hidden = $("sheetApp").dataset.canImport !== "true" || !["queue_unavailable", "temporary_processing_error", "unexpected_processing_error"].includes(batchStatus?.run?.error_code);
        status(batchStatus?.run?.error_message || "La cartera está guardada y se está validando o preparando. Se actualizará automáticamente.", batchStatus?.status === "failed" ? "error" : "");
      } else status(error.message, "error");
    } finally { if (token === state.requestId) { state.fetching = false; controls(); } }
  }

  function confirmChanges() {
    if (state.busy || state.fetching) return;
    if (!state.dirty.size) { status("No hay modificaciones por guardar."); return; }
    if (!state.data?.capabilities.edit) { status("Tu usuario no puede guardar cambios en esta cartera.", "error"); return; }
    if (grid?.pending()) { status("Espera a que termine el guardado del formato antes de confirmar los datos.", "error"); return; }
    grid?.hideFloating();
    $("confirmChangesSummary").textContent = `${state.dirty.size} filas pendientes. La descarga incluirá todo el ${state.scope === "problem" ? "conjunto de revisión" : "lote principal"}. Los cambios protegidos requieren la aprobación correspondiente.`;
    $("confirmSaveStatus").textContent = "";
    $("confirmSaveStatus").classList.remove("error");
    if (!$("confirmChangesDialog").open) $("confirmChangesDialog").showModal();
    $("changeReason").focus();
  }

  async function save(downloadAfter = false) {
    if (!$("confirmChangesDialog").open || !state.dirty.size || state.busy) return;
    const reason = $("changeReason").value.trim();
    if (reason.length < 3) { $("confirmSaveStatus").textContent = "Escribe un motivo de entre 3 y 500 caracteres."; $("changeReason").focus(); return; }
    const scope = state.scope;
    state.gridRestore = gridPosition();
    state.busy = true; controls(); status("Validando y guardando cambios…");
    $("confirmSaveStatus").textContent = "Guardando…";
    $("gridWrap").inert = true;
    let saved = false, refreshed = false, message = "";
    try {
      const result = await api(`${base()}save/`, { reason, changes: [...state.dirty.values()] });
      saved = true; state.dirty.clear(); undo.clear();
      $("confirmChangesDialog").close(); $("changeReason").value = "";
      state.busy = false;
      refreshed = await loadRows();
      message = `${result.applied.length} filas guardadas. ${result.pending.length} solicitudes enviadas a aprobación.`;
      if (!refreshed) { state.data = null; message += " El guardado fue confirmado, pero no se pudo actualizar la hoja. Pulsa Actualizar antes de descargar."; }
      status(message, refreshed ? "success" : "error");
    } catch (error) {
      $("confirmSaveStatus").textContent = `${error.message} Tus borradores se conservan.`;
      $("confirmSaveStatus").classList.add("error");
      status(`${error.message} Los cambios pendientes siguen en pantalla.`, "error");
    }
    finally {
      state.busy = false; $("gridWrap").inert = false;
      if (state.gridRestore) { restoreGridPosition(state.gridRestore); state.gridRestore = null; }
      controls();
    }
    if (saved && refreshed && downloadAfter) await download(scope, message);
  }

  async function download(scope, savedMessage = "") {
    if (!canNavigate() || !state.data) return;
    const expected = state.data.summary[scope];
    if (!expected) { status(`No hay registros en ${scope === "clean" ? "el lote principal" : "el conjunto de revisión"}. No se generó un archivo vacío.`); return; }
    grid?.hideFloating();
    state.busy = true; controls(); status("Preparando Excel con todas las filas del conjunto seleccionado…");
    try {
      const response = await fetch(`${base()}download/`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ scope, revision: state.data.summary.revision }), signal: AbortSignal.timeout(300000)
      });
      if (response.redirected || response.status === 401) throw new Error("La sesión terminó. Inicia sesión nuevamente.");
      if (!response.ok) {
        const payload = (response.headers.get("content-type") || "").includes("json") ? await response.json() : {};
        throw new Error(payload.error?.message || "No se pudo descargar el lote.");
      }
      if (!(response.headers.get("content-type") || "").includes("spreadsheetml")) throw new Error("La sesión terminó. Inicia sesión nuevamente.");
      const count = Number(response.headers.get("X-ARNOLD-Export-Rows"));
      if (count !== expected) throw new Error("El servidor no confirmó la cantidad esperada de filas. Actualiza la cartera antes de reintentar.");
      const blob = await response.blob();
      const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
      if (blob.size < 100 || signature[0] !== 80 || signature[1] !== 75 || signature[2] !== 3 || signature[3] !== 4) throw new Error("El servidor no devolvió un Excel válido. No se inició la descarga.");
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url;
      anchor.download = `ARNOLD_${scope}_${state.batch.period}_r${state.data.summary.revision}.xlsx`;
      document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
      status(`${savedMessage ? savedMessage + " " : ""}Descarga iniciada: ${count.toLocaleString("es-EC")} filas de ${scope === "clean" ? "lote principal" : "errores y duplicados"}.`, "success");
    } catch (error) { status(`${savedMessage ? savedMessage + " " : ""}No se pudo descargar: ${error.name === "TimeoutError" ? "se agotó el tiempo; reintenta la descarga" : error.message}`, "error"); }
    finally { state.busy = false; controls(); }
  }

  async function loadLog(view) {
    if (!state.batch) return;
    const target = view === "approvals" ? $("approvalList") : $("historyList");
    target.textContent = "Consultando…";
    try {
      const result = await api(`${base()}${view === "approvals" ? "requests" : "history"}/`);
      const rows = result.requests || result.edits;
      target.replaceChildren();
      if (!rows.length) { target.textContent = "No hay movimientos registrados para esta cartera."; return; }
      for (const item of rows) {
        const article = document.createElement("article"); const title = document.createElement("strong");
        title.textContent = `Fila ${item.source_row} · ${item.requester || item.user} · ${item.status || new Date(item.date).toLocaleString("es-EC")}`;
        article.append(title);
        const changes = item.changes || Object.entries(item.values).map(([field, value]) => ({ field, old: item.old[field], new: value }));
        for (const change of changes) { const p = document.createElement("p"); p.textContent = `${labels[change.field] || change.field}: ${change.old} → ${change.new}`; article.append(p); }
        const reason = document.createElement("p"); reason.textContent = `Motivo: ${item.reason}`; article.append(reason);
        if (item.can_decide) for (const approve of [true, false]) {
          const button = document.createElement("button"); button.className = "sheet-btn"; button.textContent = approve ? "Aprobar" : "Rechazar";
          button.onclick = async () => {
            button.disabled = true;
            try { await api(`${base()}requests/${item.id}/decide/`, { approve }); await loadRows(); await loadLog(view); }
            catch (error) { status(error.message, "error"); button.disabled = false; }
          };
          article.append(button);
        }
        target.append(article);
      }
    } catch (error) { target.textContent = error.message; }
  }

  function bind() {
    grid = new window.ArnoldGrid({
      context: () => state, api, notify: status, changed: controls,
      undo: undoDraft,
      cellText: (r, field) => {
        const row = state.data.rows[r];
        if (field === "#") return row.source_row;
        if (field === "QUALITY") return row.quality === "clean" ? "Sin observaciones" : "Requiere revisión";
        if (field === "TOTAL") return $("gridBody").rows[r]?.querySelector("[data-total]")?.textContent || "";
        if (field === "ERRORS") return row.errors.map(error => error.message).join(" · ");
        return valueFor(row, field);
      },
      paste: changes => {
        undo.record(changes.map(change => ({id: change.row.id, field: change.field, before: valueFor(change.row, change.field), after: change.value})));
        for (const change of changes) {
          const input = $("gridBody").rows[change.r].cells[change.c].querySelector(".cell-editor");
          input.value = change.value; editCell(change.row, change.field, change.value, input, false);
        }
        controls();
      }
    });
    grid.updateStatus();
    let preference = null;
    try { preference = localStorage.getItem("arnold.sidebarCollapsed"); } catch { /* Navegación privada. */ }
    setSidebar(preference == null ? matchMedia("(max-width: 760px)").matches : preference === "true", false);
    $("sidebarToggle").onclick = () => setSidebar(!$("sheetApp").classList.contains("sidebar-collapsed"));
    $("focusToggle").onclick = () => setFocusMode(!state.focusMode);
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && state.focusMode && !document.querySelector("dialog[open]")) {
        event.preventDefault(); setFocusMode(false); $("focusToggle").focus();
      }
    });
    $("refreshButton").onclick = () => loadBatches(state.batch?.id);
    $("retryButton").onclick = async () => {
      if (!canNavigate() || !state.batch) return;
      state.busy = true; controls();
      try { await api(`/api/v1/batches/${state.batch.id}/retry/`, {}); state.busy = false; await loadBatches(state.batch.id); }
      catch (error) { status(error.message, "error"); }
      finally { state.busy = false; controls(); }
    };
    $("batchSelect").onchange = async event => {
      if (!canNavigate()) { event.target.value = state.batch?.id || ""; return; }
      state.batch = state.batches.find(batch => batch.id === event.target.value); state.page = 1; state.data = null;
      state.resetGridPosition = true;
      localStorage.setItem("arnold.selectedBatch", state.batch.id); await loadRows();
      if (state.view !== "grid") await loadLog(state.view);
    };
    document.querySelectorAll("[data-scope]").forEach(button => button.onclick = async () => {
      if (!canNavigate()) return;
      state.scope = button.dataset.scope; state.page = 1;
      state.resetGridPosition = true;
      document.querySelectorAll("[data-scope]").forEach(other => other.classList.toggle("active", other === button)); await loadRows();
    });
    document.querySelectorAll("[data-view]").forEach(button => button.onclick = () => {
      state.view = button.dataset.view;
      if (state.view !== "grid") setFocusMode(false);
      $("sheetSecondary").hidden = state.view !== "grid";
      $("sheetMain").scrollTop = 0;
      for (const view of ["grid", "approvals", "history"]) $(`${view}View`).hidden = state.view !== view;
      document.querySelectorAll("[data-view]").forEach(other => other.classList.toggle("active", other === button));
      if (state.view !== "grid") loadLog(state.view);
    });
    $("searchForm").onsubmit = async event => { event.preventDefault(); if (!canNavigate()) return; state.search = $("searchInput").value.trim(); state.page = 1; state.resetGridPosition = true; await loadRows(); };
    $("previousPage").onclick = async () => { if (canNavigate()) { state.page--; state.resetGridPosition = true; await loadRows(); } };
    $("nextPage").onclick = async () => { if (canNavigate()) { state.page++; state.resetGridPosition = true; await loadRows(); } };
    $("saveButton").onclick = confirmChanges;
    $("confirmChangesForm").onsubmit = event => { event.preventDefault(); save(event.submitter?.value === "download"); };
    $("cancelChanges").onclick = () => { if (!state.busy) $("confirmChangesDialog").close(); };
    $("confirmChangesDialog").addEventListener("cancel", event => { if (state.busy) event.preventDefault(); });
    $("discardButton").onclick = () => { state.dirty.clear(); renderRows(); controls(); status("Cambios locales descartados. Se conservan los últimos valores guardados."); };
    $("downloadClean").onclick = () => download("clean"); $("downloadProblems").onclick = () => download("problem");
    document.addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); confirmChanges(); } });
    window.addEventListener("beforeunload", event => { if (state.dirty.size || state.busy || grid?.pending()) { event.preventDefault(); event.returnValue = ""; } });
    $("importButton").onclick = () => { if (canNavigate()) $("uploadDialog").showModal(); };
    $("closeUpload").onclick = () => { if (!state.busy) $("uploadDialog").close(); };
    $("uploadForm").onsubmit = upload;
  }

  async function upload(event) {
    event.preventDefault();
    if (state.busy) return;
    const file = $("uploadFile").files[0], maximum = Number($("sheetApp").dataset.maxBytes);
    if (!file || !file.name.toLowerCase().endsWith(".xlsx") || file.size > maximum) { $("uploadStatus").textContent = "Selecciona un .xlsx dentro del límite de 50 MB."; return; }
    const form = new FormData();
    for (const [name, value] of Object.entries({ file, period: $("uploadPeriod").value, sheet_name: $("uploadSheet").value.trim(),
      header_row: $("uploadHeader").value, schema_name: "carteraMensual", profile_id: $("uploadProfile").value,
      reference_batch_id: $("uploadReference").value })) form.append(name, value);
    state.busy = true; controls(); $("uploadSubmit").disabled = true; $("uploadProgress").hidden = false;
    $("uploadStatus").textContent = "Enviando archivo…";
    try {
      const result = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest(); xhr.open("POST", "/api/v1/batches/uploads/"); xhr.timeout = 300000;
        xhr.setRequestHeader("X-CSRFToken", csrf()); xhr.setRequestHeader("Accept", "application/json");
        xhr.upload.onprogress = progress => { if (progress.lengthComputable) { $("uploadProgress").value = progress.loaded / progress.total * 100; $("uploadStatus").textContent = progress.loaded === progress.total ? "Archivo enviado. Registrando y comprobando seguridad…" : `Enviando ${Math.round(progress.loaded / progress.total * 100)} %`; } };
        xhr.onerror = () => reject(new Error("No se pudo enviar el archivo. Comprueba que el servidor esté activo y que Excel no bloquee su lectura."));
        xhr.ontimeout = () => reject(new Error("Se agotó el tiempo de carga. Consulta la lista antes de volver a enviar el archivo."));
        xhr.onload = () => {
          let payload; try { payload = JSON.parse(xhr.responseText); } catch { reject(new Error("El servidor no devolvió una respuesta válida. Comprueba tu sesión.")); return; }
          if (xhr.status >= 200 && xhr.status < 300) resolve(payload);
          else { const error = new Error(payload.error?.message || "La carga fue rechazada."); error.payload = payload; reject(error); }
        }; xhr.send(form);
      });
      $("uploadStatus").textContent = "Cartera recibida. Se actualizará al terminar la validación.";
      $("uploadDialog").close(); state.busy = false; await loadBatches(result.batch_id);
    } catch (error) {
      $("uploadStatus").textContent = error.message;
      if (error.payload?.existing_batch_id || error.payload?.batch_id) { state.busy = false; await loadBatches(error.payload.existing_batch_id || error.payload.batch_id); }
    } finally { state.busy = false; $("uploadSubmit").disabled = false; controls(); }
  }

  async function start() {
    try {
      bind(); await loadBatches();
      setInterval(() => { if (!document.hidden && !state.busy && !state.fetching && !state.dirty.size && state.view === "grid" && !document.activeElement?.closest("#gridWrap")) loadRows(true); }, 10000);
    } catch (error) { status(`No se pudo iniciar la hoja: ${error.message}`, "error"); }
  }
  start();
})();
