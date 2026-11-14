/* Developer Assistant: the browser half of the Workspace (Phase 5).
 *
 * Only the browser can touch the developer's laptop, and only after he picks the folder himself.
 * This file collects FACTS about the folder, runs a WRITE JOB the server approved, and builds the
 * ZIP / upload fallback. It decides nothing: the Python server turns facts into blockers and
 * keeps the record. It is read as text by da_workspace_bridge.py and run by Dash clientside
 * callbacks, so CodeVision's own assets folder needs no change.
 *
 * AS400 picture: this is the job on the developer's workstation that can read the library. The
 * server holds the change form; this file only does what the form allows.
 */
(function () {
  if (window.daWorkspace) { return; }

  const ABSENT = "absent";
  const DB_NAME = "da_workspace";
  const STORE = "handles";
  const KEY = "handle";

  // --- fingerprint: the same rules as Python (decision D-G) ---

  function normalise(text) {
    if (text.charCodeAt(0) === 0xFEFF) { text = text.slice(1); }
    return text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  }

  async function fingerprint(text) {
    const bytes = new TextEncoder().encode(normalise(text));
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // --- paths (rule W3): plain relative paths only ---

  function pathProblem(path) {
    if (!path || path !== path.trim()) { return "The path is empty."; }
    if (path.includes("\\") || path.startsWith("/") || path.includes(":")) {
      return path + ": only plain relative paths with / are allowed.";
    }
    for (const part of path.split("/")) {
      if (part === "" || part === "." || part === "..") {
        return path + ": '..', '.' and empty parts are not allowed.";
      }
    }
    return "";
  }

  // --- the remembered folder (decision D-B): the handle lives in this browser only ---

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function saveHandle(handle) {
    try {
      const db = await openDb();
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(handle, KEY);
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
      });
    } catch (error) { /* remembering is a convenience; the pick itself already worked */ }
  }

  async function loadHandle() {
    try {
      const db = await openDb();
      return await new Promise((resolve, reject) => {
        const request = db.transaction(STORE).objectStore(STORE).get(KEY);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error);
      });
    } catch (error) { return null; }
  }

  // W4: on page load only ASK whether permission is still there; never prompt without a click.
  async function permissionOf(handle) {
    if (!handle || !handle.queryPermission) { return "unknown"; }
    return handle.queryPermission({ mode: "readwrite" });
  }

  async function ensurePermission(handle) {
    if (await permissionOf(handle) === "granted") { return true; }
    return (await handle.requestPermission({ mode: "readwrite" })) === "granted";
  }

  // --- walking the folder ---

  async function dirAt(root, parts) {
    let dir = root;
    for (const part of parts) {
      try { dir = await dir.getDirectoryHandle(part); } catch (error) { return null; }
    }
    return dir;
  }

  async function fileAt(root, path) {
    const parts = path.split("/");
    const name = parts.pop();
    const dir = await dirAt(root, parts);
    if (!dir) { return { dir: null, file: null }; }
    try { return { dir, file: await dir.getFileHandle(name) }; }
    catch (error) { return { dir, file: null }; }
  }

  // Read one File object: size first (too big is never read), then strict UTF-8.
  async function readFileObject(file, maxKb) {
    if (file.size > maxKb * 1024) { return { too_big: true }; }
    try {
      const text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      return { text, fingerprint: await fingerprint(text) };
    } catch (error) { return { not_utf8: true }; }
  }

  async function readHandleText(root, path) {
    const found = await fileAt(root, path);
    if (!found.file) { return null; }
    const file = await found.file.getFile();
    return new TextDecoder().decode(await file.arrayBuffer());
  }

  // --- the facts (spec section 4): the browser collects, the server judges ---

  async function collectFacts(root, ctx) {
    const markers = {};
    for (const marker of ctx.markers) { markers[marker] = !!(await dirAt(root, marker.split("/"))); }
    const stripped = ctx.markers.map((m) => m.replace(/^src\//, ""));
    let aboveSrc = stripped.length > 0;
    for (const marker of stripped) { if (!(await dirAt(root, marker.split("/")))) { aboveSrc = false; } }
    const facts = {
      folder_name: root.name || "folder",
      markers,
      looks_like_src: aboveSrc && !Object.values(markers).some(Boolean),
      has_git: await hasGit(root),
      files: [],
    };
    for (const path of ctx.planned_paths) {
      const parts = path.split("/");
      parts.pop();
      const parent = parts.length === 0 || !!(await dirAt(root, parts));
      const found = await fileAt(root, path);
      if (!found.file) { facts.files.push({ path, exists: false, parent_exists: parent }); continue; }
      const file = await found.file.getFile();
      facts.files.push({ path, exists: true, parent_exists: true, ...(await readFileObject(file, ctx.max_file_kb)) });
    }
    return facts;
  }

  async function hasGit(root) {
    // Only asks whether the entry exists. The .git folder is never opened.
    try { await root.getDirectoryHandle(".git"); return true; } catch (error) { /* try as a file */ }
    try { await root.getFileHandle(".git"); return true; } catch (error) { return false; }
  }

  // --- the write job (spec section 5) ---

  async function runJob(root, job) {
    const report = { written: [], stopped: null };
    const allowed = new Set(job.files.map((f) => f.path));
    for (const item of job.files) {
      const reason = await writeOne(root, item, allowed);
      if (typeof reason === "string") { report.stopped = { path: item.path, reason }; break; }
      report.written.push(reason);
    }
    return report;
  }

  // Returns a stop reason (string) or the written record. Every guard is checked here AND on
  // the server (rule W3).
  async function writeOne(root, item, allowed) {
    const problem = pathProblem(item.path);
    if (problem || !allowed.has(item.path)) { return item.path + " is not allowed."; }
    const parts = item.path.split("/");
    const name = parts.pop();
    let dir = root;
    let walked = "";
    for (const part of parts) {
      walked = walked ? walked + "/" + part : part;
      // The writer creates NO folders at all (Phase 6, C2): a missing folder is a refusal.
      try { dir = await dir.getDirectoryHandle(part); }
      catch (error) {
        return "The folder " + walked + " does not exist, and the app does not create it.";
      }
    }
    // The edit guard (R5.1): the file must still be what the server last saw.
    let current = null;
    let handleNow = null;
    try { handleNow = await dir.getFileHandle(name); } catch (error) { handleNow = null; }
    if (handleNow) {
      try {
        const bytes = await (await handleNow.getFile()).arrayBuffer();
        current = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } catch (error) { return item.path + " is not a UTF-8 text file. Re-scan first."; }
    }
    if (item.expected === ABSENT) {
      if (current !== null) { return item.path + " already exists. Re-scan first."; }
    } else if (current === null || (await fingerprint(current)) !== item.expected) {
      return item.path + " changed since last time. Re-scan first.";
    }
    try {
      const handle = await dir.getFileHandle(name, { create: true });
      const writable = await handle.createWritable();
      await writable.write(item.text);
      await writable.close();
    } catch (error) { return "Could not write " + item.path + ": " + error.message; }
    const back = await readHandleText(root, item.path);
    return { path: item.path, text: back, fingerprint: await fingerprint(back) };
  }

  // --- the picker and the actions the screen starts ---

  let root = null;  // the folder in use on this page; never sent to the server

  function pickerAvailable() { return !!window.showDirectoryPicker && window.isSecureContext; }

  // `linking` is true only for the Change button: the developer says "yes, link this one".
  async function choose(ctx, remembered, linking) {
    if (!pickerAvailable()) { return { kind: "fallback", reason: "unsupported" }; }
    let handle;
    try {
      if (remembered) {
        handle = await loadHandle();
        if (!handle || !(await ensurePermission(handle))) { return { kind: "cancelled" }; }
      } else {
        handle = await window.showDirectoryPicker({ id: "codevision", mode: "readwrite" });
        if (!(await ensurePermission(handle))) { return { kind: "fallback", reason: "refused" }; }
      }
    } catch (error) {
      if (error && error.name === "AbortError") { return { kind: "cancelled" }; }
      return { kind: "fallback", reason: "refused" };
    }
    // P26: a different folder that has the same NAME as the linked one is not the linked folder.
    // isSameEntry compares the folders themselves, so only a real second folder is stopped.
    if (!remembered && !linking && ctx.folder_name && handle.name === ctx.folder_name) {
      const previous = await loadHandle();
      if (previous && !(await handle.isSameEntry(previous))) {
        return { kind: "different_folder", name: handle.name };
      }
    }
    root = handle;
    await saveHandle(handle);
    return { kind: "facts", facts: await collectFacts(root, ctx) };
  }

  // Reconnect (W4): the chip said "Needs your OK". Re-allow the remembered folder; with none
  // remembered, fall back to the picker. Returns "reconnected" so the screen only redraws.
  async function reconnect(ctx) {
    const remembered = await loadHandle();
    if (!remembered) { return choose(ctx, false, false); }
    if (!(await ensurePermission(remembered))) { return { kind: "cancelled" }; }
    root = remembered;
    return { kind: "reconnected" };
  }

  async function scan(ctx) {
    const handle = root || (await loadHandle());
    if (!handle || !(await ensurePermission(handle))) { return { kind: "cancelled" }; }
    root = handle;
    return { kind: "scan_facts", facts: await collectFacts(root, ctx) };
  }

  // Runs a job the server approved. After a page reload `root` is empty, so the remembered folder
  // is used, but only if permission is STILL granted: this never asks (it may run without a
  // click, for the automatic write at the end of a build, D-E). With no folder it reports
  // `not_connected`, which the server does NOT save as a stopped write.
  async function write(job) {
    const handle = root || (await loadHandle());
    if (!handle || (await permissionOf(handle)) !== "granted") {
      return { written: [], stopped: null, not_connected: true };
    }
    root = handle;
    return runJob(root, job);
  }

  // Which button was pressed on the screen. Called straight from the click, so the picker works.
  async function handle(key, ctx) {
    if (key === "change_folder") { return choose(ctx, false, true); }
    if (key === "choose" || key === "retry_picker") { return choose(ctx, false, false); }
    if (key === "use_remembered") { return choose(ctx, true); }
    if (key === "reconnect") { return reconnect(ctx); }
    if (key === "rescan") { return scan(ctx); }
    if (key === "build" || key === "rebuild") {
      // The pre-build re-scan (B1): read the planned files, then the server starts the build.
      // In download mode there is no folder handle, so the re-scan is the folder upload.
      const found = ctx.mode === "download" ? await upload(ctx) : await scan(ctx);
      if (found.kind !== "scan_facts" && found.kind !== "upload_facts") { return found; }
      return { ...found, kind: key === "build" ? "build_facts" : "rebuild_facts" };
    }
    // Phase 9 freshness buttons: read ONLY the confirmed target(s) (ctx.planned_paths is the
    // server's list, 9-48), then the server compares them with main. Nothing is written.
    if (key.startsWith("enhance_")) {
      let found = ctx.mode === "download" || !pickerAvailable() ? await upload(ctx) : await scan(ctx);
      // No folder remembered yet: this click may open the picker, then read the same files.
      if (found.kind === "cancelled" && pickerAvailable()) { found = await choose(ctx, false, false); }
      if (found.kind === "facts") { found = { ...found, kind: "scan_facts" }; }
      // Anything but facts (cancelled, refused, different folder) changes nothing on the server.
      if (found.kind !== "scan_facts" && found.kind !== "upload_facts") { return { kind: "enhance_cancelled" }; }
      return { ...found, kind: key };
    }
    // Phase 10 Handoff final check: read ONLY the planned files, then the server compares them with
    // the last test. Download mode has no folder handle, so the check is the folder upload.
    if (key === "handoff_check") {
      let found = ctx.mode === "download" || !pickerAvailable() ? await upload(ctx) : await scan(ctx);
      if (found.kind !== "scan_facts" && found.kind !== "upload_facts") { return { kind: "handoff_cancelled" }; }
      return { ...found, kind: "handoff_facts" };
    }
    if (key === "build_download") { return { kind: "build_download" }; }
    // Phase 8 Restore build N: the server holds the build number (ctx.restore_build). Nothing is
    // read from the folder; the edit guard of the write job protects his files.
    if (key === "restore_go") {
      return { kind: ctx.mode === "download" ? "restore_download" : "restore_write" };
    }
    if (key === "download") { return { kind: "download" }; }
    if (key === "upload") { return upload(ctx); }
    return { kind: "cancelled" };
  }

  // What the header chip shows on page load (W4): only a permission QUERY, never a prompt.
  async function chip() {
    const remembered = await loadHandle();
    if (!remembered) { return { name: "", permission: "none" }; }
    return { name: remembered.name, permission: await permissionOf(remembered) };
  }

  // --- fallback: upload a folder (spec section 7). Only planned files are read. ---

  function upload(ctx) {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.webkitdirectory = true;
      input.multiple = true;
      input.style.display = "none";
      document.body.appendChild(input);
      input.addEventListener("change", async () => {
        const files = Array.from(input.files);
        input.remove();
        if (files.length === 0) { resolve({ kind: "cancelled" }); return; }
        resolve({ kind: "upload_facts", facts: await factsFromUpload(files, ctx) });
      });
      input.addEventListener("cancel", () => { input.remove(); resolve({ kind: "cancelled" }); });
      input.click();
    });
  }

  async function factsFromUpload(files, ctx) {
    const byPath = new Map();
    let folderName = "folder";
    for (const file of files) {
      const parts = file.webkitRelativePath.split("/");
      folderName = parts.shift();
      byPath.set(parts.join("/"), file);
    }
    const keys = Array.from(byPath.keys());
    const under = (folder) => keys.some((k) => k === folder || k.startsWith(folder + "/"));
    const markers = {};
    for (const marker of ctx.markers) { markers[marker] = under(marker); }
    const stripped = ctx.markers.map((m) => m.replace(/^src\//, ""));
    const aboveSrc = stripped.length > 0 && stripped.every(under) && !Object.values(markers).some(Boolean);
    const facts = {
      folder_name: folderName, markers, looks_like_src: aboveSrc, has_git: under(".git"),
      files: [],
    };
    for (const path of ctx.planned_paths) {
      const parent = path.includes("/") ? under(path.slice(0, path.lastIndexOf("/"))) : true;
      const file = byPath.get(path);
      if (!file) { facts.files.push({ path, exists: false, parent_exists: parent }); continue; }
      facts.files.push({ path, exists: true, parent_exists: true, ...(await readFileObject(file, ctx.max_file_kb)) });
    }
    return facts;
  }

  // --- fallback: a ZIP of the write job, built here with no library (stored, no compression) ---

  const CRC_TABLE = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) { c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; }
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    let crc = 0xFFFFFFFF;
    for (const byte of bytes) { crc = CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >>> 8); }
    return (crc ^ 0xFFFFFFFF) >>> 0;
  }

  function makeZip(entries) {
    const encoder = new TextEncoder();
    const chunks = [];
    const central = [];
    let offset = 0;
    const DOS_DATE = ((2026 - 1980) << 9) | (11 << 5) | 1;
    for (const entry of entries) {
      const name = encoder.encode(entry.name);
      const data = encoder.encode(entry.text);
      const crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30));
      local.setUint32(0, 0x04034B50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);
      local.setUint16(8, 0, true); local.setUint16(10, 0, true); local.setUint16(12, DOS_DATE, true);
      local.setUint32(14, crc, true); local.setUint32(18, data.length, true); local.setUint32(22, data.length, true);
      local.setUint16(26, name.length, true); local.setUint16(28, 0, true);
      chunks.push(new Uint8Array(local.buffer), name, data);
      const head = new DataView(new ArrayBuffer(46));
      head.setUint32(0, 0x02014B50, true); head.setUint16(4, 20, true); head.setUint16(6, 20, true);
      head.setUint16(8, 0x0800, true); head.setUint16(10, 0, true); head.setUint16(12, 0, true);
      head.setUint16(14, DOS_DATE, true); head.setUint32(16, crc, true); head.setUint32(20, data.length, true);
      head.setUint32(24, data.length, true); head.setUint16(28, name.length, true);
      head.setUint32(42, offset, true);
      central.push(new Uint8Array(head.buffer), name);
      offset += 30 + name.length + data.length;
    }
    let centralSize = 0;
    for (const part of central) { centralSize += part.length; }
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054B50, true); end.setUint16(8, entries.length, true);
    end.setUint16(10, entries.length, true); end.setUint32(12, centralSize, true);
    end.setUint32(16, offset, true);
    return new Blob([...chunks, ...central, new Uint8Array(end.buffer)], { type: "application/zip" });
  }

  function download(pack) {
    const entries = pack.files.map((f) => ({ name: f.path, text: f.text }));
    entries.push({ name: pack.readme_name, text: pack.readme });
    const url = URL.createObjectURL(makeZip(entries));
    const link = document.createElement("a");
    link.href = url;
    link.download = "developer-assistant-files.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  window.daWorkspace = { fingerprint, normalise, pathProblem, handle, write, chip, download };
})();
