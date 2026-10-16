/* Interacciones de presentación. Los cambios de datos usan el controlador original. */
(() => {
  "use strict";
  const M = window.ArnoldSheetModel, $ = id => document.getElementById(id);
  class ArnoldGrid {
    constructor(adapter) {
      this.adapter = adapter; this.doc = M.blank(); this.selection = new M.Selection();
      this.columns = []; this.queue = []; this.saving = null; this.failed = false; this.batch = null;
      this.editing = false; this.resize = null; this.drag = null; this.timer = null; this.paintFrame = null;
      this.pointerSelection = false; this.menuAnchor = null;
      this.bind();
    }
    context() { return this.adapter.context(); }
    pending() { return !!this.queue.length || !!this.saving; }
    canFormat() { return !!this.context().data?.capabilities.format && !this.context().busy && !this.context().fetching; }
    rendered(data, columns) {
      this.hideFloating(); this.editing = false;
      const batch = this.context().batch.id;
      if (batch !== this.batch) { this.selection.clear(); this.batch = batch; }
      this.columns = columns;
      this.selection.setRows(data.rows, columns);
      if (!this.pending()) this.doc = structuredClone(data.presentation || M.blank());
      this.installHandles(); this.paint(); this.paintSelection(); this.updateStatus();
    }
    receivePresentation(document) {
      if (!this.pending() && document && document.version !== this.doc.version) {
        this.doc = structuredClone(document); this.paint(); this.paintSelection();
      }
    }
    change(operations) {
      if (!this.canFormat()) { this.adapter.notify("Tu usuario no puede guardar formato en esta cartera.", "error"); return; }
      if (!operations.length) { this.adapter.notify("Selecciona primero una celda o un rango."); return; }
      M.apply(this.doc, operations); this.queue.push(...operations); this.failed = false;
      this.paint(); this.paintSelection(); this.updateStatus(); this.adapter.changed();
      clearTimeout(this.timer); this.timer = setTimeout(() => this.flush(), 650);
    }
    async flush() {
      clearTimeout(this.timer);
      if (this.saving) return this.saving;
      if (!this.queue.length) return true;
      this.saving = this.persist(); this.updateStatus(); this.adapter.changed();
      const result = await this.saving;
      this.saving = null; this.updateStatus(); this.adapter.changed();
      if (result && this.queue.length) return this.flush();
      return result;
    }
    async persist() {
      const operations = []; let cost = 0;
      while (this.queue.length && operations.length < 100) {
        const next = this.queue[0], amount = (next.columns?.length || 1) * (next.rows?.length || 1);
        if (cost + amount > 10000) break;
        operations.push(this.queue.shift()); cost += amount;
      }
      const version = this.doc.version;
      try {
        const response = await this.adapter.api(`/api/v1/worksheets/${this.batch}/presentation/`, {version, operations});
        this.doc.version = response.version; this.failed = false; return true;
      } catch (error) {
        this.queue.unshift(...operations); this.failed = true;
        this.adapter.notify(`${error.message} El formato pendiente se conserva en esta pestaña. Usa Guardar formato o Actualizar formato.`, "error");
        return false;
      }
    }
    async refreshPresentation() {
      if (this.saving || !this.context().data) return;
      try {
        const response = await this.adapter.api(`/api/v1/worksheets/${this.batch}/presentation/`, {rows: this.context().data.rows.map(row => row.id)});
        this.doc = M.apply(response.presentation, this.queue);
        this.failed = false; this.paint(); await this.flush();
      } catch (error) { this.adapter.notify(error.message, "error"); }
    }
    updateStatus() {
      $("formatStatus").textContent = this.failed ? "Formato pendiente: reintentar" : this.pending() ? "Guardando formato…" : "Formato guardado";
      $("formatStatus").classList.toggle("error", this.failed);
      $("formatSave").disabled = !this.queue.length || !!this.saving || !this.canFormat();
      for (const control of $("formatToolbar").querySelectorAll("[data-format], [data-format-setting], .format-swatch")) control.disabled = !this.canFormat();
    }
    installHandles() {
      const headers = [...$("gridHead").querySelectorAll("th")];
      headers.forEach((th, c) => {
        th.dataset.c = c;
        const handle = document.createElement("span"); handle.className = "column-resizer";
        handle.dataset.resizeColumn = c; handle.tabIndex = this.canFormat() ? 0 : -1;
        handle.setAttribute("role", "separator"); handle.setAttribute("aria-orientation", "vertical");
        handle.setAttribute("aria-label", `Ancho de ${this.columns[c].label}`);
        handle.title = "Arrastra para cambiar el ancho. Doble clic: ajustar al contenido de esta página. Flechas: ±10 px.";
        th.append(handle);
      });
      [...$("gridBody").rows].forEach((tr, r) => {
        if (!tr.dataset.row) return;
        tr.dataset.r = r;
        [...tr.cells].forEach((td, c) => { td.dataset.r = r; td.dataset.c = c; td.setAttribute("aria-selected", "false"); });
        const handle = document.createElement("span"); handle.className = "row-resizer"; handle.dataset.resizeRow = r;
        handle.tabIndex = this.canFormat() ? 0 : -1; handle.setAttribute("role", "separator");
        handle.setAttribute("aria-orientation", "horizontal"); handle.setAttribute("aria-label", `Altura de fila ${this.selection.rows[r].source_row}`);
        handle.title = "Arrastra para cambiar la altura. Doble clic: ajustar fila. Flechas: ±4 px.";
        tr.cells[0].append(handle);
      });
    }
    paint() {
      const table = $("dataGrid"); table.style.zoom = this.doc.zoom / 100;
      if (![...$("sheetZoom").options].some(option => option.value === String(this.doc.zoom))) $("sheetZoom").add(new Option(`${this.doc.zoom} %`, this.doc.zoom));
      $("sheetZoom").value = this.doc.zoom;
      let total = 0;
      [...$("gridHead").querySelectorAll("th")].forEach((th, c) => {
        const column = this.columns[c], width = this.doc.columns[column.field]?.width || column.width;
        th.style.width = `${width}px`; th.querySelector(".column-resizer")?.setAttribute("aria-valuenow", width); total += width;
      });
      table.style.width = `${total}px`; table.style.minWidth = `${total}px`;
      [...$("gridBody").rows].forEach((tr, r) => {
        const row = this.selection.rows[r]; if (!row) return;
        let height = this.doc.heights[row.id] || 29;
        if (!this.doc.heights[row.id]) this.columns.forEach((column, c) => {
          const visual = M.style(this.doc, row.id, column.field);
          if (!visual.size && !visual.wrap) return;
          const width = this.doc.columns[column.field]?.width || column.width;
          const lines = visual.wrap ? String(this.text(r, c)).split("\n").reduce((sum, line) => sum + Math.max(1, Math.ceil(this.measure(line, visual) / Math.max(20, width - 16))), 0) : 1;
          height = Math.max(height, Math.ceil(M.clamp(lines * (visual.size || 12) * 1.4 + 8, 24, 240)));
        });
        tr.style.height = `${height}px`;
        tr.querySelector(".row-resizer")?.setAttribute("aria-valuenow", height);
        [...tr.cells].forEach((td, c) => {
          const style = M.style(this.doc, row.id, this.columns[c].field);
          td.style.backgroundColor = style.background || ""; td.style.color = style.color || "";
          td.style.fontWeight = style.bold ? "700" : ""; td.style.fontStyle = style.italic ? "italic" : "";
          td.style.textDecoration = style.underline ? "underline" : ""; td.style.textAlign = style.align || "";
          td.style.fontSize = style.size ? `${style.size}px` : ""; td.style.height = `${height}px`;
          td.classList.toggle("cell-custom-color", !!style.color);
          td.classList.toggle("cell-custom-font", ["bold", "italic", "underline", "size"].some(key => key in style));
          td.classList.toggle("cell-custom-alignment", !!style.align);
          td.classList.toggle("cell-wrap", !!style.wrap);
          const editor = td.querySelector(".cell-editor"); if (editor) editor.style.height = `${height - 1}px`;
        });
      });
    }
    scheduleSelection() {
      if (!this.paintFrame) this.paintFrame = requestAnimationFrame(() => { this.paintFrame = null; this.paintSelection(); });
    }
    paintSelection() {
      const active = this.selection.active;
      for (const td of $("gridBody").querySelectorAll("td[data-c]")) {
        const r = Number(td.dataset.r), c = Number(td.dataset.c), selected = this.selection.has(r, c);
        td.classList.toggle("cell-selected", selected); td.classList.toggle("cell-active", active?.r === r && active?.c === c);
        td.setAttribute("aria-selected", String(selected));
        td.classList.toggle("range-top", selected && !this.selection.has(r - 1, c));
        td.classList.toggle("range-bottom", selected && !this.selection.has(r + 1, c));
        td.classList.toggle("range-left", selected && !this.selection.has(r, c - 1));
        td.classList.toggle("range-right", selected && !this.selection.has(r, c + 1));
      }
      const bounds = this.selection.bounds();
      $("rangeAddress").value = bounds ? `${this.address(bounds.r1, bounds.c1)}:${this.address(bounds.r2, bounds.c2)}` : "";
      $("rangeAddress").title = this.selection.ranges.some(r => r.scope === "columns") ? "Columnas completas: el formato se aplica a todas las páginas." : "Rango de la página visible; usa Shift o Ctrl para ampliar.";
      const style = active ? M.style(this.doc, this.selection.rows[active.r].id, this.columns[active.c].field) : {};
      if (active) {
        const size = String(style.size || 12);
        if (![...$("fontSize").options].some(option => option.value === size)) $("fontSize").add(new Option(size, size));
        $("fontSize").value = size;
        $("cellAlignment").value = style.align || (this.columns[active.c].field.startsWith("TOTAL") ? "right" : "left");
        $("fillColor").value = style.background || "#ffffff";
        $("textColor").value = style.color || "#213b4d";
      }
      for (const button of $("formatToolbar").querySelectorAll("[data-format]")) {
        button.setAttribute("aria-pressed", String(!!style[button.dataset.format]));
      }
    }
    address(r, c) { return `${c ? String.fromCharCode(64 + c) : "#"}${this.selection.rows[r]?.source_row ?? ""}`; }
    focusActive() {
      const point = this.selection.active; if (!point) return;
      const td = $("gridBody").rows[point.r]?.cells[point.c];
      const editor = td?.querySelector(".cell-editor");
      if (editor && this.editing) editor.focus();
      else { $("gridWrap").focus({preventScroll: true}); td?.scrollIntoView({block: "nearest", inline: "nearest"}); }
    }
    beginEdit() {
      const point = this.selection.active, data = this.context().data;
      if (!point || !data?.capabilities.edit || !data.fields.includes(this.columns[point.c].field)) return;
      this.hideFloating(); this.editing = true; this.focusActive();
    }
    hideFloating() {
      $("formatToolbar").hidden = true; this.pointerSelection = false;
      for (const panel of $("formatToolbar").querySelectorAll(".format-panel")) panel.hidden = true;
      for (const button of $("formatToolbar").querySelectorAll("[data-panel]")) button.setAttribute("aria-expanded", "false");
    }
    showFloating() {
      if (this.resize || this.drag || this.editing || !this.selection.active || this.context().view !== "grid") return;
      const wrap = $("gridWrap").getBoundingClientRect(), points = [];
      for (const td of $("gridBody").querySelectorAll("td.cell-selected")) {
        const rect = td.getBoundingClientRect();
        if (rect.right > wrap.left && rect.left < wrap.right && rect.bottom > wrap.top && rect.top < wrap.bottom)
          points.push({left: Math.max(rect.left, wrap.left), top: Math.max(rect.top, wrap.top), right: Math.min(rect.right, wrap.right), bottom: Math.min(rect.bottom, wrap.bottom)});
      }
      if (!points.length) return;
      const anchor = this.menuAnchor = {left: Math.min(...points.map(p => p.left)), top: Math.min(...points.map(p => p.top)), bottom: Math.max(...points.map(p => p.bottom))};
      const toolbar = $("formatToolbar"); toolbar.hidden = false;
      const left = M.clamp(anchor.left, 8, Math.max(8, innerWidth - toolbar.offsetWidth - 8));
      let top = anchor.top - toolbar.offsetHeight - 8;
      if (top < 8) top = anchor.bottom + 8;
      // Si el rango llena la pantalla, usa el espacio superior de la hoja.
      if (top + toolbar.offsetHeight > innerHeight - 8) top = Math.max(8, wrap.top - toolbar.offsetHeight - 8);
      Object.assign(toolbar.style, {left: `${left}px`, top: `${top}px`});
      this.updateStatus(); this.paintSelection();
    }
    togglePanel(id) {
      const panel = $(id), open = panel.hidden;
      for (const other of $("formatToolbar").querySelectorAll(".format-panel")) other.hidden = true;
      for (const button of $("formatToolbar").querySelectorAll("[data-panel]")) button.setAttribute("aria-expanded", String(open && button.dataset.panel === id));
      if (!open) return;
      panel.hidden = false;
      const rect = $("formatToolbar").getBoundingClientRect();
      panel.style.maxHeight = `${Math.max(100, Math.max(rect.top - 16, innerHeight - rect.bottom - 16))}px`;
      const above = rect.top - panel.offsetHeight - 6;
      const preferAbove = this.menuAnchor && rect.bottom <= this.menuAnchor.top;
      const top = (preferAbove && above >= 8) || innerHeight - rect.bottom < panel.offsetHeight + 8
        ? Math.max(8, above) : rect.bottom + 6;
      panel.style.left = `${M.clamp(rect.left, 8, Math.max(8, innerWidth - panel.offsetWidth - 8))}px`;
      panel.style.top = `${top}px`;
    }
    async copy() {
      try { await navigator.clipboard.writeText(this.copyText()); }
      catch { this.adapter.notify("El navegador no dio acceso al portapapeles. Usa Ctrl+C en la selección.", "error"); }
    }
    format(patch, reset = false) { this.change(this.selection.operations(patch, reset)); }
    toggle(key) {
      const active = this.selection.active; if (!active) return this.adapter.notify("Selecciona una celda o rango.");
      const enabled = !M.style(this.doc, this.selection.rows[active.r].id, this.columns[active.c].field)[key];
      this.format({[key]: enabled});
      if (key === "wrap" && enabled) this.autoHeight();
    }
    selectedRows() {
      const ids = new Set();
      for (const range of this.selection.ranges) for (let r = range.r1; r <= range.r2; r++) ids.add(this.selection.rows[r].id);
      return [...ids];
    }
    selectedColumns() {
      const fields = new Set();
      for (const range of this.selection.ranges) for (let c = range.c1; c <= range.c2; c++) fields.add(this.columns[c].field);
      return [...fields];
    }
    text(r, c) { return this.adapter.cellText(r, this.columns[c].field); }
    copyText() {
      const bounds = this.selection.bounds(); if (!bounds) return "";
      const output = [];
      for (let r = bounds.r1; r <= bounds.r2; r++) {
        const row = []; for (let c = bounds.c1; c <= bounds.c2; c++) row.push(this.selection.has(r, c) ? this.text(r, c) : "");
        output.push(row);
      }
      return M.encodeTSV(output);
    }
    paste(text) {
      const data = this.context().data, active = this.selection.active;
      if (!data?.capabilities.edit || !active) throw new Error("Selecciona una celda editable y comprueba tus permisos.");
      const matrix = M.parseTSV(text), changes = [];
      if (matrix.length === 1 && matrix[0].length === 1) {
        for (let r = 0; r < data.rows.length; r++) for (let c = 0; c < this.columns.length; c++)
          if (this.selection.has(r, c)) changes.push({r, c, value: matrix[0][0]});
      } else {
        if (this.selection.ranges.length > 1) throw new Error("Para pegar un bloque selecciona un solo rango continuo.");
        const start = this.selection.bounds();
        matrix.forEach((row, dr) => row.forEach((value, dc) => changes.push({r: start.r1 + dr, c: start.c1 + dc, value})));
      }
      if (!changes.length || changes.some(item => !data.rows[item.r] || !data.fields.includes(this.columns[item.c]?.field)))
        throw new Error("El pegado excede la página o incluye columnas calculadas/no editables. No se cambió ninguna celda.");
      this.adapter.paste(changes.map(item => ({row: data.rows[item.r], field: this.columns[item.c].field, value: item.value, r: item.r, c: item.c})));
      this.adapter.notify("Rango pegado como borrador. Revisa las alertas y usa Guardar cambios; los campos protegidos mantienen su aprobación.");
    }
    measure(text, style = {}) {
      this.canvas ||= document.createElement("canvas"); const ctx = this.canvas.getContext("2d");
      ctx.font = `${style.bold ? "bold " : ""}${style.size || 12}px Segoe UI, Arial`;
      return Math.max(...String(text).split("\n").map(line => ctx.measureText(line).width), 0);
    }
    autoWidth(fields = this.selectedColumns()) {
      this.change(fields.map(field => {
        const c = this.columns.findIndex(column => column.field === field);
        let width = this.measure(this.columns[c].label, {bold: true}) + 25;
        this.selection.rows.forEach((row, r) => width = Math.max(width, this.measure(this.text(r, c), M.style(this.doc, row.id, field)) + 22));
        return {kind: "width", columns: [field], value: Math.round(M.clamp(width, 55, 800))};
      }));
    }
    autoHeight(ids = this.selectedRows()) {
      this.change(ids.map(id => {
        const r = this.selection.rows.findIndex(row => row.id === id); let height = 29;
        this.columns.forEach((col, c) => {
          const style = M.style(this.doc, id, col.field), width = this.doc.columns[col.field]?.width || col.width;
          const lines = style.wrap ? String(this.text(r, c)).split("\n").reduce((sum, line) => sum + Math.max(1, Math.ceil(this.measure(line, style) / Math.max(20, width - 16))), 0) : 1;
          height = Math.max(height, lines * (style.size || 12) * 1.4 + 8);
        });
        return {kind: "height", rows: [id], value: Math.ceil(M.clamp(height, 24, 240))};
      }));
    }
    point(target) {
      const td = target.closest("#gridBody td[data-c]");
      return td ? {r: Number(td.dataset.r), c: Number(td.dataset.c)} : null;
    }
    startResize(event, handle) {
      this.hideFloating();
      if (!this.canFormat() || event.button !== 0) return;
      event.preventDefault(); event.stopPropagation();
      const column = handle.dataset.resizeColumn;
      const index = Number(column ?? handle.dataset.resizeRow), axis = column == null ? "y" : "x";
      const key = axis === "x" ? this.columns[index].field : this.selection.rows[index].id;
      this.resize = {axis, key, origin: axis === "x" ? event.clientX : event.clientY,
        initial: axis === "x" ? this.doc.columns[key]?.width || this.columns[index].width : this.doc.heights[key] || 29};
      this.resize.value = this.resize.initial;
      this.showGuide(axis, axis === "x" ? event.clientX : event.clientY);
      $("gridWrap").classList.add("grid-resizing");
    }
    showGuide(axis, coordinate) {
      const rect = $("gridWrap").getBoundingClientRect(), guide = $("resizeGuide");
      guide.hidden = false; guide.className = `resize-guide ${axis}`;
      Object.assign(guide.style, axis === "x" ? {left: `${coordinate}px`, top: `${rect.top}px`, width: "2px", height: `${rect.height}px`}
        : {left: `${rect.left}px`, top: `${coordinate}px`, width: `${rect.width}px`, height: "2px"});
    }
    contextMenu(event) {
      const point = this.point(event.target); if (!point) return;
      event.preventDefault(); this.hideFloating();
      if (!this.selection.has(point.r, point.c)) this.selection.choose(point.r, point.c);
      this.paintSelection(); this.editing = false;
      const menu = $("gridContextMenu"); menu.hidden = false;
      for (const item of menu.querySelectorAll("[data-context]")) {
        const action = item.dataset.context;
        item.disabled = ["paste", "edit"].includes(action) ? !this.context().data.capabilities.edit || !this.context().data.fields.includes(this.columns[point.c].field)
          : action !== "copy" && !this.canFormat();
      }
      menu.style.left = `${Math.min(event.clientX, innerWidth - 195)}px`;
      menu.style.top = `${Math.min(event.clientY, Math.max(5, innerHeight - menu.offsetHeight - 5))}px`;
      menu.querySelector("button:not(:disabled)")?.focus();
    }
    bind() {
      const wrap = $("gridWrap"), toolbar = $("formatToolbar");
      wrap.addEventListener("pointerdown", event => {
        const handle = event.target.closest(".column-resizer, .row-resizer"); if (handle) return this.startResize(event, handle);
        if (event.button !== 0) return;
        const editingPoint = this.point(event.target);
        if (this.editing && editingPoint && this.selection.active?.r === editingPoint.r && this.selection.active?.c === editingPoint.c
            && !event.shiftKey && !event.ctrlKey && !event.metaKey) return;
        this.hideFloating(); this.editing = false;
        const header = event.target.closest("#gridHead th");
        if (header) {
          event.preventDefault(); const c = Number(header.dataset.c);
          if (event.shiftKey && this.selection.active) this.selection.selectColumns(this.selection.active.c, c, event.ctrlKey || event.metaKey);
          else this.selection.selectColumns(c, c, event.ctrlKey || event.metaKey);
          wrap.focus({preventScroll: true}); this.pointerSelection = true; this.paintSelection(); return;
        }
        const point = this.point(event.target); if (!point) return;
        this.editing = false;
        if (point.c === 0) {
          event.preventDefault(); this.selection.selectRows(event.shiftKey && this.selection.active ? this.selection.active.r : point.r, point.r, event.ctrlKey || event.metaKey);
          wrap.focus({preventScroll: true}); this.pointerSelection = true; this.paintSelection(); return;
        }
        this.selection.choose(point.r, point.c, {shift: event.shiftKey, add: event.ctrlKey || event.metaKey});
        event.preventDefault(); wrap.focus({preventScroll: true}); this.pointerSelection = true;
        this.drag = {point: this.selection.anchor, x: event.clientX, y: event.clientY, moved: false}; this.paintSelection();
      });
      document.addEventListener("pointermove", event => {
        if (this.resize) {
          event.preventDefault(); const resize = this.resize, coordinate = resize.axis === "x" ? event.clientX : event.clientY;
          resize.value = Math.round(M.clamp(resize.initial + (coordinate - resize.origin) / (this.doc.zoom / 100), resize.axis === "x" ? 40 : 24, resize.axis === "x" ? 800 : 240));
          this.showGuide(resize.axis, resize.origin + (resize.value - resize.initial) * this.doc.zoom / 100); return;
        }
        if (!this.drag || !(event.buttons & 1)) return;
        if (Math.hypot(event.clientX - this.drag.x, event.clientY - this.drag.y) < 4) return;
        const target = document.elementFromPoint(event.clientX, event.clientY), point = target && this.point(target);
        if (point) {
          this.drag.moved = true; event.preventDefault(); this.selection.choose(point.r, point.c, {shift: true});
          this.scheduleSelection();
          const rect = wrap.getBoundingClientRect();
          if (event.clientY > rect.bottom - 22) wrap.scrollTop += 15;
          if (event.clientY < rect.top + 45) wrap.scrollTop -= 15;
          if (event.clientX > rect.right - 22) wrap.scrollLeft += 20;
          if (event.clientX < rect.left + 65) wrap.scrollLeft -= 20;
        }
      });
      document.addEventListener("pointerup", () => {
        if (this.resize) {
          const resize = this.resize; this.resize = null;
          $("resizeGuide").hidden = true; wrap.classList.remove("grid-resizing");
          this.change([{kind: resize.axis === "x" ? "width" : "height", [resize.axis === "x" ? "columns" : "rows"]: [resize.key], value: resize.value}]);
        }
        const selected = this.pointerSelection || this.drag?.moved;
        if (this.drag?.moved) { window.getSelection()?.removeAllRanges(); wrap.focus({preventScroll: true}); }
        this.drag = null;
        this.pointerSelection = false;
        if (selected) { this.paintSelection(); this.showFloating(); }
      });
      wrap.addEventListener("dblclick", event => {
        const column = event.target.closest("[data-resize-column]"), row = event.target.closest("[data-resize-row]");
        if (column) this.autoWidth([this.columns[Number(column.dataset.resizeColumn)].field]);
        else if (row) this.autoHeight([this.selection.rows[Number(row.dataset.resizeRow)].id]);
        else if (event.target.closest(".cell-editor")) this.beginEdit();
      });
      wrap.addEventListener("keydown", event => this.key(event));
      wrap.addEventListener("focusin", event => {
        const point = this.point(event.target);
        if (point && !this.selection.has(point.r, point.c)) { this.selection.choose(point.r, point.c); this.paintSelection(); }
      });
      wrap.addEventListener("copy", event => {
        if (this.editing || !this.selection.ranges.length) return;
        event.preventDefault(); event.clipboardData.setData("text/plain", this.copyText());
      });
      wrap.addEventListener("paste", event => {
        if (this.editing) return;
        event.preventDefault(); try { this.paste(event.clipboardData.getData("text/plain")); } catch (error) { this.adapter.notify(error.message, "error"); }
      });
      wrap.addEventListener("contextmenu", event => this.contextMenu(event));
      toolbar.addEventListener("pointerdown", event => {
        // Evita que un botón robe el foco a la tabla; inputs y selects sí son operables.
        if (event.target.closest("button")) event.preventDefault();
      });
      toolbar.addEventListener("click", event => {
        const panel = event.target.closest("[data-panel]");
        if (panel && !panel.disabled) this.togglePanel(panel.dataset.panel);
        const format = event.target.closest("[data-format]"), swatch = event.target.closest("[data-fill], [data-text]");
        if (format) this.toggle(format.dataset.format);
        if (swatch && !swatch.disabled) {
          this.format(swatch.dataset.fill ? {background: swatch.dataset.fill} : {color: swatch.dataset.text});
          this.togglePanel(swatch.closest(".format-panel").id);
        }
      });
      for (const [id, key] of [["fillColor", "background"], ["textColor", "color"], ["fontSize", "size"], ["cellAlignment", "align"]])
        $(id).addEventListener("change", event => {
          this.format({[key]: key === "size" ? Number(event.target.value) : event.target.value});
          if (key === "size") this.autoHeight();
        });
      $("clearFormat").onclick = () => this.format({}, true);
      $("clearSelection").onclick = () => { this.selection.clear(); this.paintSelection(); this.hideFloating(); wrap.focus({preventScroll: true}); };
      $("selectRow").onclick = () => { if (this.selection.active) this.selection.selectRows(this.selection.active.r); this.paintSelection(); };
      $("selectColumn").onclick = () => { if (this.selection.active) this.selection.selectColumns(this.selection.active.c); this.paintSelection(); };
      $("selectRange").onclick = () => this.selectAddress();
      $("rangeAddress").onkeydown = event => { if (event.key === "Enter") { event.preventDefault(); this.selectAddress(); } };
      $("autoWidth").onclick = () => this.autoWidth(); $("autoHeight").onclick = () => this.autoHeight();
      $("resetSizes").onclick = () => this.change([{kind: "reset_sizes"}]);
      $("sheetZoom").onchange = event => this.change([{kind: "zoom", value: Number(event.target.value)}]);
      $("formatSave").onclick = () => this.flush(); $("formatRefresh").onclick = () => this.refreshPresentation();
      $("showFullText").onclick = () => this.showFullText();
      $("copySelection").onclick = () => this.copy();
      $("undoDraft").onclick = () => this.adapter.undo();
      $("closeCellText").onclick = () => $("cellTextDialog").close();
      $("gridContextMenu").addEventListener("click", event => this.contextAction(event));
      document.addEventListener("pointerdown", event => {
        if (!event.target.closest("#gridContextMenu")) $("gridContextMenu").hidden = true;
        if (!event.target.closest("#formatToolbar, #gridWrap")) this.hideFloating();
      });
      document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !toolbar.hidden) {
          event.preventDefault(); event.stopImmediatePropagation(); this.hideFloating(); wrap.focus({preventScroll: true});
        }
      });
      toolbar.addEventListener("keydown", event => {
        if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "z" && !event.target.matches("input, select")) {
          event.preventDefault(); this.adapter.undo();
        }
      });
      $("gridContextMenu").addEventListener("keydown", event => {
        const buttons = [...$("gridContextMenu").querySelectorAll("button:not(:disabled)")], index = buttons.indexOf(document.activeElement);
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); buttons[(index + (event.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length]?.focus(); }
        if (event.key === "Escape") { event.stopPropagation(); $("gridContextMenu").hidden = true; this.focusActive(); }
      });
      const dismiss = () => { $("gridContextMenu").hidden = true; this.hideFloating(); };
      wrap.addEventListener("scroll", dismiss, {passive: true});
      $("sheetMain").addEventListener("scroll", dismiss, {passive: true});
      window.addEventListener("resize", dismiss);
      document.addEventListener("pointercancel", () => {
        this.hideFloating(); this.resize = null; this.drag = null; $("resizeGuide").hidden = true; wrap.classList.remove("grid-resizing");
      });
    }
    key(event) {
      const handle = event.target.closest("[data-resize-column], [data-resize-row]");
      if (handle && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        event.preventDefault(); const column = handle.dataset.resizeColumn, index = Number(column ?? handle.dataset.resizeRow);
        const key = column == null ? this.selection.rows[index].id : this.columns[index].field;
        const value = column == null ? this.doc.heights[key] || 29 : this.doc.columns[key]?.width || this.columns[index].width;
        this.change([{kind: column == null ? "height" : "width", [column == null ? "rows" : "columns"]: [key], value: M.clamp(value + (["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1) * (column == null ? 4 : 10), column == null ? 24 : 40, column == null ? 240 : 800)}]); return;
      }
      if ((event.ctrlKey || event.metaKey) && ["b", "i", "u"].includes(event.key.toLowerCase())) {
        event.preventDefault(); this.toggle({b: "bold", i: "italic", u: "underline"}[event.key.toLowerCase()]); return;
      }
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "z") {
        event.preventDefault(); this.adapter.undo(); return;
      }
      if (event.key === "F2") { event.preventDefault(); this.beginEdit(); return; }
      if (event.key === "Escape") {
        if (!$("formatToolbar").hidden) { event.preventDefault(); event.stopPropagation(); this.hideFloating(); }
        this.editing = false; $("gridWrap").focus({preventScroll: true}); return;
      }
      if (this.editing && !["Tab", "Enter"].includes(event.key)) return;
      const active = this.selection.active || {r: 0, c: 2};
      const delta = {ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0], Enter: [event.shiftKey ? -1 : 1, 0], Tab: [0, event.shiftKey ? -1 : 1]}[event.key];
      if (!delta || event.ctrlKey || event.metaKey || event.altKey) return;
      event.preventDefault(); this.hideFloating(); this.editing = false;
      let r = active.r + delta[0], c = active.c + delta[1];
      if (event.key === "Tab") { if (c >= this.columns.length) { c = 0; r++; } if (c < 0) { c = this.columns.length - 1; r--; } }
      this.selection.choose(r, c, {shift: event.shiftKey && event.key.startsWith("Arrow")}); this.paintSelection(); this.focusActive();
    }
    selectAddress() {
      const match = /^([A-Q])(\d+)(?::([A-Q])(\d+))?$/i.exec($("rangeAddress").value.trim());
      if (!match) return this.adapter.notify("Escribe un rango visible, por ejemplo D2:F5.", "error");
      const r1 = this.selection.rows.findIndex(row => row.source_row === Number(match[2]));
      const r2 = this.selection.rows.findIndex(row => row.source_row === Number(match[4] || match[2]));
      if (r1 < 0 || r2 < 0) return this.adapter.notify("El rango debe pertenecer a las 100 filas de la página actual.", "error");
      this.selection.choose(r1, match[1].toUpperCase().charCodeAt(0) - 64);
      this.selection.choose(r2, (match[3] || match[1]).toUpperCase().charCodeAt(0) - 64, {shift: true}); this.paintSelection(); this.focusActive();
    }
    showFullText() {
      const point = this.selection.active; if (!point) return;
      $("cellTextContent").textContent = this.text(point.r, point.c);
      $("cellTextTitle").textContent = `${this.columns[point.c].label} · fila ${this.selection.rows[point.r].source_row}`;
      this.hideFloating(); $("cellTextDialog").showModal();
    }
    async contextAction(event) {
      const button = event.target.closest("[data-context]"); if (!button || button.disabled) return;
      const action = button.dataset.context; $("gridContextMenu").hidden = true;
      try {
        if (action === "copy") await this.copy();
        if (action === "paste") this.paste(await navigator.clipboard.readText());
        if (action === "edit") this.beginEdit();
        if (action === "highlight") this.format({background: "#FFF2CC"});
        if (action === "color") { this.showFloating(); this.togglePanel("fillPalette"); }
        if (action === "bold" || action === "underline") this.toggle(action);
        if (action === "width") this.autoWidth(); if (action === "height") this.autoHeight();
        if (action === "clear") this.format({}, true);
      } catch (error) { this.adapter.notify("El navegador no dio acceso al portapapeles. Usa Ctrl+C o Ctrl+V con una celda enfocada.", "error"); }
    }
  }
  window.ArnoldGrid = ArnoldGrid;
})();
