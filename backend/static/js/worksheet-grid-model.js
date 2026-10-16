/* Modelo de selección/presentación. No calcula ni almacena importes. */
((root) => {
  "use strict";
  const blank = () => ({version: 0, columns: {}, heights: {}, cells: {}, zoom: 100});
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const rectangle = (a, b, scope = "cells") => ({r1: Math.min(a.r, b.r), r2: Math.max(a.r, b.r), c1: Math.min(a.c, b.c), c2: Math.max(a.c, b.c), scope});
  const contains = (range, r, c) => r >= range.r1 && r <= range.r2 && c >= range.c1 && c <= range.c2;
  function parseTSV(text) {
    const rows = [[]]; let value = "", quoted = false;
    text = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (char === '"' && (quoted || !value)) {
        if (quoted && text[i + 1] === '"') { value += '"'; i++; } else quoted = !quoted;
      } else if (!quoted && (char === "\t" || char === "\n")) {
        rows.at(-1).push(value); value = "";
        if (char === "\n") rows.push([]);
      } else value += char;
    }
    if (quoted) throw new Error("El texto copiado tiene comillas sin cerrar.");
    rows.at(-1).push(value);
    if (text.endsWith("\n") && rows.at(-1).length === 1 && rows.at(-1)[0] === "") rows.pop();
    if (rows.length > 100 || rows.some(row => row.length > 18 || row.some(cell => cell.length > 1000))) throw new Error("El pegado supera 100 filas, 18 columnas o 1.000 caracteres por celda.");
    return rows;
  }
  const encodeTSV = rows => rows.map(row => row.map(value => {
    const text = String(value ?? "");
    return /[\t\n\r"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }).join("\t")).join("\n");
  function apply(document, operations) {
    for (const op of operations) {
      if (op.kind === "cells") for (const id of op.rows) {
        const row = document.cells[id] ||= {};
        for (const field of op.columns) row[field] = op.reset ? {reset: true} : {...row[field], ...op.style};
      }
      if (op.kind === "columns") for (const field of op.columns) {
        const col = document.columns[field] ||= {};
        col.style = op.reset ? {} : {...col.style, ...op.style};
        for (const row of Object.values(document.cells)) if (row[field]) {
          if (op.reset) delete row[field];
          else { delete row[field].reset; for (const key of Object.keys(op.style)) delete row[field][key]; }
        }
      }
      if (op.kind === "width") for (const field of op.columns) (document.columns[field] ||= {}).width = op.value;
      if (op.kind === "height") for (const id of op.rows) document.heights[id] = op.value;
      if (op.kind === "zoom") document.zoom = op.value;
      if (op.kind === "reset_sizes") { document.heights = {}; document.zoom = 100; for (const col of Object.values(document.columns)) delete col.width; }
    }
    return document;
  }
  const style = (document, id, field) => {
    const cell = document.cells[id]?.[field] || {};
    const result = {...(cell.reset ? {} : document.columns[field]?.style), ...cell};
    delete result.reset; return result;
  };
  // Solo memoria de la pestaña: jamás revierte guardados, aprobaciones ni formato.
  class DraftUndo {
    constructor(limit = 50, budget = 1048576) { this.limit = limit; this.budget = budget; this.clear(); }
    clear() { this.actions = []; }
    get available() { return this.actions.length > 0; }
    record(changes, mergeKey = null, now = Date.now()) {
      changes = changes.filter(change => change.before !== change.after).map(change => ({...change}));
      if (!changes.length) return;
      const previous = this.actions.at(-1);
      if (mergeKey && previous?.key === mergeKey && now - previous.time < 1200 && changes.length === 1
          && previous.changes[0].after === changes[0].before) {
        previous.changes[0].after = changes[0].after; previous.time = now;
        if (previous.changes[0].before === previous.changes[0].after) this.actions.pop();
      } else this.actions.push({changes, key: mergeKey, time: now});
      while (this.actions.length > this.limit || JSON.stringify(this.actions).length > this.budget) this.actions.shift();
    }
    take() { return this.actions.pop()?.changes || []; }
  }
  class Selection {
    constructor(rows = [], columns = []) { this.rows = rows; this.columns = columns; this.clear(); }
    clear() { this.ranges = []; this.active = null; this.anchor = null; }
    setRows(rows, columns) {
      const unchanged = this.rows.length === rows.length && this.rows.every((row, index) => row.id === rows[index].id)
        && this.columns.length === columns.length && this.columns.every((col, index) => col.field === columns[index].field);
      const id = this.active && this.rows[this.active.r]?.id;
      const field = this.active && this.columns[this.active.c]?.field;
      this.rows = rows; this.columns = columns;
      if (unchanged) return;
      const r = rows.findIndex(row => row.id === id), c = columns.findIndex(column => column.field === field);
      if (r < 0 || c < 0) this.clear(); else this.choose(r, c);
    }
    choose(r, c, {shift = false, add = false} = {}) {
      if (!this.rows.length || !this.columns.length) return;
      const point = {r: clamp(r, 0, this.rows.length - 1), c: clamp(c, 0, this.columns.length - 1)};
      if (shift && this.anchor) {
        const range = rectangle(this.anchor, point);
        if (this.ranges.length) this.ranges[this.ranges.length - 1] = range; else this.ranges.push(range);
      } else {
        if (!add) this.ranges = [];
        this.ranges.push(rectangle(point, point)); this.anchor = point;
      }
      this.active = point;
    }
    selectRows(r1, r2 = r1, add = false) {
      if (!this.rows.length) return;
      if (!add) this.ranges = [];
      this.ranges.push(rectangle({r: r1, c: 0}, {r: r2, c: this.columns.length - 1}, "rows"));
      this.anchor = this.active = {r: r1, c: 2};
    }
    selectColumns(c1, c2 = c1, add = false) {
      if (!this.rows.length) return;
      if (!add) this.ranges = [];
      this.ranges.push(rectangle({r: 0, c: c1}, {r: this.rows.length - 1, c: c2}, "columns"));
      this.anchor = this.active = {r: 0, c: c1};
    }
    has(r, c) { return this.ranges.some(range => contains(range, r, c)); }
    operations(patch, reset = false) {
      return this.ranges.map(range => ({kind: range.scope === "columns" ? "columns" : "cells",
        ...(range.scope === "columns" ? {} : {rows: this.rows.slice(range.r1, range.r2 + 1).map(row => row.id)}),
        columns: this.columns.slice(range.c1, range.c2 + 1).map(col => col.field), style: patch, reset}));
    }
    bounds() {
      if (!this.ranges.length) return null;
      return {r1: Math.min(...this.ranges.map(r => r.r1)), r2: Math.max(...this.ranges.map(r => r.r2)),
        c1: Math.min(...this.ranges.map(r => r.c1)), c2: Math.max(...this.ranges.map(r => r.c2))};
    }
  }
  const api = {blank, clamp, rectangle, contains, parseTSV, encodeTSV, apply, style, Selection, DraftUndo};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ArnoldSheetModel = api;
})(typeof window === "undefined" ? globalThis : window);
