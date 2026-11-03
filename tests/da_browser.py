"""Helpers for tests that need a real browser (Playwright, Chromium).

Every browser test is SKIPPED, not failed, when Playwright or its browser is missing, so a plain
laptop run stays green. The skip text says which rows were not proven (plan decision P16).

The folder picker cannot be clicked in a headless browser, so the page gets a stand-in: it
returns the browser's private test folder (a real folder handle). No switch is added to the app.
"""

import pytest

from web.da_workspace_bridge import workspace_script

SKIP_TEXT = (
    "Playwright or its browser not found: "
    "the real-browser rows (5-15, 5-16, 5-23, 5-24, 5-27) are NOT proven"
)
ORIGIN = "http://127.0.0.1:8765/"

# Keeps real folder handles in memory instead of IndexedDB, which crashes headless Chromium
# (found in plan step 1). Plain values still go to the real IndexedDB.
INIT_SCRIPT = """
(() => {
  const mem = new Map();
  const put = IDBObjectStore.prototype.put;
  const get = IDBObjectStore.prototype.get;
  const real = Object.getOwnPropertyDescriptor(IDBRequest.prototype, 'result').get;
  IDBObjectStore.prototype.put = function (value, key) {
    if (value instanceof FileSystemHandle) {
      mem.set(this.name + '/' + key, value);
      return put.call(this, { __mem: true }, key);
    }
    return put.call(this, value, key);
  };
  IDBObjectStore.prototype.get = function (key) {
    const request = get.call(this, key);
    const name = this.name;
    Object.defineProperty(request, 'result', { configurable: true, get() {
      const found = real.call(request);
      return found && found.__mem ? mem.get(name + '/' + key) : found;
    }});
    return request;
  };
  // Records which files the page opened, so a test can prove an unrelated file was never read.
  window.__opened = [];
  const getFile = FileSystemFileHandle.prototype.getFile;
  FileSystemFileHandle.prototype.getFile = function () {
    window.__opened.push(this.name);
    return getFile.call(this);
  };
  const buffer = File.prototype.arrayBuffer;
  File.prototype.arrayBuffer = function () {
    window.__opened.push(this.webkitRelativePath || this.name);
    return buffer.call(this);
  };
})();
"""
PICKER_SCRIPT = "window.showDirectoryPicker = async () => navigator.storage.getDirectory();"


@pytest.fixture(scope="session")
def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip(SKIP_TEXT)
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch()
    except Exception:  # the browser itself is missing or cannot start
        playwright.stop()
        pytest.skip(SKIP_TEXT)
    yield browser
    browser.close()
    playwright.stop()


@pytest.fixture
def make_page(_chromium):
    """Open a fresh page on a secure origin with the browser script loaded.

    make_page(picker=True) puts the stand-in picker in place; picker=False removes it, like an
    old browser. Each call is a new browser context, so the private folder starts empty."""
    contexts = []

    def build(picker: bool = True):
        context = _chromium.new_context(accept_downloads=True)
        contexts.append(context)
        page = context.new_page()
        page.route(ORIGIN + "**", lambda route: route.fulfill(
            status=200, content_type="text/html", body="<!doctype html><title>t</title>"
        ))
        page.add_init_script(INIT_SCRIPT)
        page.add_init_script(
            PICKER_SCRIPT if picker else "delete window.showDirectoryPicker;"
        )
        page.goto(ORIGIN)
        page.add_script_tag(content=workspace_script())
        return page

    yield build
    for context in contexts:
        context.close()


# Put files into the private folder: {"src/web/a.py": "text"}.
SEED_JS = """
async (files) => {
  const root = await navigator.storage.getDirectory();
  for (const [path, text] of Object.entries(files)) {
    const parts = path.split('/');
    const name = parts.pop();
    let dir = root;
    for (const part of parts) { dir = await dir.getDirectoryHandle(part, { create: true }); }
    const handle = await dir.getFileHandle(name, { create: true });
    const writable = await handle.createWritable();
    await writable.write(text);
    await writable.close();
  }
}
"""

# Read one file's exact text back, or null if it is not there.
READ_JS = """
async (path) => {
  let dir = await navigator.storage.getDirectory();
  const parts = path.split('/');
  const name = parts.pop();
  try {
    for (const part of parts) { dir = await dir.getDirectoryHandle(part); }
    return await (await (await dir.getFileHandle(name)).getFile()).text();
  } catch (error) { return null; }
}
"""

# Does a folder exist in the private folder?
HAS_DIR_JS = """
async (path) => {
  let dir = await navigator.storage.getDirectory();
  try {
    for (const part of path.split('/')) { dir = await dir.getDirectoryHandle(part); }
    return true;
  } catch (error) { return false; }
}
"""


@pytest.fixture
def make_live_page(_chromium):
    """Open a page of a running app (not the blank test page). Same stand-ins as make_page."""
    contexts = []

    def build(url: str, picker: bool = True):
        context = _chromium.new_context(accept_downloads=True)
        contexts.append(context)
        page = context.new_page()
        page.add_init_script(INIT_SCRIPT)
        page.add_init_script(PICKER_SCRIPT if picker else "delete window.showDirectoryPicker;")
        page.goto(url)
        return page

    yield build
    for context in contexts:
        context.close()
