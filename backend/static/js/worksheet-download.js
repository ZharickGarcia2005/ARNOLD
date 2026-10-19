/* Validación compartida de descargas; no reintenta ni ejecuta guardados. */
(function (root) {
  "use strict";
  function filename(disposition) {
    const extended = /filename\*=UTF-8''([^;]+)/i.exec(disposition || "");
    const quoted = /filename="([^"]+)"/i.exec(disposition || "");
    let name = extended ? decodeURIComponent(extended[1]) : quoted?.[1];
    if (!name || name.length > 240 || /[\\/\x00-\x1f]/.test(name) || !name.endsWith(".xlsx")) throw new Error("El servidor no confirmó un nombre Excel seguro.");
    return name;
  }
  async function receive(response, {batch, revision, expected}) {
    if (response.redirected || response.status === 401) throw new Error("La sesión terminó. Inicia sesión nuevamente.");
    if (!response.ok) {
      const payload = (response.headers.get("content-type") || "").includes("json") ? await response.json() : {};
      throw new Error(payload.error?.message || "No se pudo descargar el lote.");
    }
    if (!(response.headers.get("content-type") || "").includes("spreadsheetml")) throw new Error("El servidor no devolvió un Excel. Comprueba la sesión.");
    const count = Number(response.headers.get("X-ARNOLD-Export-Rows"));
    if (!Number.isSafeInteger(count) || count <= 0 || count !== expected
        || Number(response.headers.get("X-ARNOLD-Export-Revision")) !== revision
        || response.headers.get("X-ARNOLD-Export-Batch") !== batch) throw new Error("El servidor no confirmó el lote, la revisión o la cantidad de filas. Actualiza antes de reintentar.");
    const name = filename(response.headers.get("Content-Disposition"));
    const blob = await response.blob();
    const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
    if (blob.size < 100 || signature[0] !== 80 || signature[1] !== 75 || signature[2] !== 3 || signature[3] !== 4) throw new Error("El servidor no devolvió un Excel válido. No se inició la descarga.");
    return {blob, name, count};
  }
  const api = {filename, receive};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ArnoldDownload = api;
})(typeof window !== "undefined" ? window : globalThis);
