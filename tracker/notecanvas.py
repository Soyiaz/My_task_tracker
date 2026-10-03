"""A Notability-style ink editor, as a Streamlit v2 component.

The whole editor is one HTML/CSS/JS bundle mounted through
``st.components.v2.component``. It draws on HTML canvases with pointer
events (stylus pressure included), keeps every stroke as vector data, and
hands the document back to Python as a single JSON state value — debounced,
so a page is saved a moment after the pen lifts rather than on every point.

Python side: ``mount(...)`` renders it and returns the component result;
``result.doc`` is the latest document the page sent back (or ``None``).

Document shape (``notes.empty_doc``)::

    {"v": 1, "seq": 17, "paper": "lined", "paperColor": "white",
     "pages": [{"items": [
        {"t": "s", "tool": "pen"|"hl", "c": "#000", "w": 3, "p": [[x, y, pressure], ...]},
        {"t": "x", "x": 100, "y": 80, "text": "...", "size": 22, "c": "#000"},
        {"t": "g", "k": "line"|"arrow"|"rect"|"ellipse", "x1":..,"y1":..,"x2":..,"y2":.., "c": "#000", "w": 3}
     ]}]}

Pages are 1000 × 1400 logical units (an A4-ish portrait page); zoom is
purely a view setting.
"""

from __future__ import annotations

from streamlit.components.v2 import component

HTML = r"""
<div class="nb" tabindex="0">
  <div class="nb-top">
    <div class="nb-title">
      <span class="nb-course-dot"></span>
      <span class="nb-course"></span>
      <span class="nb-name"></span>
    </div>
    <div class="nb-tools" role="toolbar"></div>
    <div class="nb-right">
      <button class="nb-ib" data-act="undo" title="Undo (Z)">
        <svg viewBox="0 0 24 24"><path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/></svg>
      </button>
      <button class="nb-ib" data-act="redo" title="Redo (Shift+Z)">
        <svg viewBox="0 0 24 24"><path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/></svg>
      </button>
      <span class="nb-sep"></span>
      <button class="nb-ib" data-act="zoomout" title="Zoom out (-)">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6"/></svg>
      </button>
      <span class="nb-zoom">100%</span>
      <button class="nb-ib" data-act="zoomin" title="Zoom in (+)">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6M11 8v6"/></svg>
      </button>
      <button class="nb-ib" data-act="fit" title="Fit page width (0)">
        <svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>
      </button>
      <span class="nb-sep"></span>
      <button class="nb-ib" data-act="addpage" title="Add a page">
        <svg viewBox="0 0 24 24"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M12 12v6M9 15h6"/></svg>
      </button>
      <button class="nb-ib" data-act="export" title="Export this page as PNG">
        <svg viewBox="0 0 24 24"><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>
      </button>
      <button class="nb-ib" data-act="save" title="Save now">
        <svg viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>
      </button>
      <span class="nb-status" title="Autosaves a moment after you stop writing">Saved</span>
    </div>
  </div>
  <div class="nb-sub">
    <div class="nb-swatches"></div>
    <div class="nb-widths"></div>
    <div class="nb-shapes"></div>
    <div class="nb-sub-right">
      <label class="nb-lbl">Paper
        <select class="nb-paper">
          <option value="lined">Lined</option>
          <option value="grid">Grid</option>
          <option value="dotted">Dotted</option>
          <option value="plain">Plain</option>
          <option value="cornell">Cornell</option>
        </select>
      </label>
      <label class="nb-lbl">
        <select class="nb-pcolor">
          <option value="white">White</option>
          <option value="cream">Cream</option>
          <option value="dark">Dark</option>
        </select>
      </label>
      <label class="nb-lbl nb-check"><input type="checkbox" class="nb-finger"> Finger draws</label>
      <span class="nb-pageinfo">Page 1 of 1</span>
    </div>
  </div>
  <div class="nb-body">
    <div class="nb-thumbs"></div>
    <div class="nb-scroll"><div class="nb-pages"></div></div>
  </div>
</div>
"""

CSS = r"""
:host { display:block; }
* { box-sizing: border-box; }
.nb {
  --accent: var(--st-primary-color, #4f46e5);
  --bg: var(--st-secondary-background-color, #f6f7fb);
  --fg: var(--st-text-color, #15161c);
  --border: var(--st-border-color, #e3e5ee);
  --radius: 10px;
  font-family: Inter, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 13px;
  color: var(--fg);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  height: 100%;
  min-height: 560px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  outline: none;
  user-select: none;
  -webkit-user-select: none;
}
.nb-top, .nb-sub {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 70%, transparent);
  flex-wrap: wrap;
}
.nb-sub { padding: 4px 10px; min-height: 38px; }
.nb-title { display:flex; align-items:center; gap:6px; min-width: 0; flex: 1 1 160px; }
.nb-course-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); flex: none; }
.nb-course { opacity: .7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px; }
.nb-name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nb-tools { display:flex; align-items:center; gap: 2px; flex: 0 0 auto; margin: 0 auto;
  background: color-mix(in srgb, var(--fg) 6%, transparent); border-radius: 12px; padding: 3px; }
.nb-right { display:flex; align-items:center; gap: 2px; flex: 1 1 160px; justify-content: flex-end; }
.nb-sep { width: 1px; height: 18px; background: var(--border); margin: 0 4px; }
.nb-ib, .nb-tb {
  appearance: none; border: 0; background: transparent; color: var(--fg);
  width: 32px; height: 30px; border-radius: 9px; display:inline-flex; align-items:center;
  justify-content:center; cursor: pointer; padding: 0; position: relative;
}
.nb-ib:hover, .nb-tb:hover { background: color-mix(in srgb, var(--fg) 9%, transparent); }
.nb-ib:disabled { opacity: .35; cursor: default; }
.nb-ib svg, .nb-tb svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
.nb-tb.active { background: var(--accent); color: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.15); }
.nb-tb .nb-tcolor { position:absolute; bottom: 3px; left: 50%; transform: translateX(-50%); width: 14px; height: 3px; border-radius: 2px; }
.nb-zoom { min-width: 42px; text-align: center; font-variant-numeric: tabular-nums; opacity: .8; }
.nb-status { font-size: 12px; opacity: .7; margin-left: 4px; min-width: 56px; text-align: right; }
.nb-status.dirty { color: #d97706; opacity: 1; }
.nb-status.saving { color: var(--accent); opacity: 1; }
.nb-swatches { display:flex; gap: 5px; align-items: center; }
.nb-sw { width: 20px; height: 20px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; padding: 0;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.12); }
.nb-sw.active { border-color: var(--fg); transform: scale(1.12); }
.nb-sw.custom { background: conic-gradient(red, yellow, lime, aqua, blue, magenta, red); position: relative; overflow: hidden; }
.nb-sw.custom input { position:absolute; inset:0; opacity: 0; width: 100%; height: 100%; cursor: pointer; }
.nb-widths { display:flex; gap: 4px; align-items:center; margin-left: 10px; }
.nb-wd { width: 28px; height: 28px; border-radius: 8px; border: 0; background: transparent; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; }
.nb-wd:hover { background: color-mix(in srgb, var(--fg) 9%, transparent); }
.nb-wd.active { background: color-mix(in srgb, var(--accent) 18%, transparent); }
.nb-wd i { display:block; border-radius: 50%; background: var(--fg); }
.nb-shapes { display:flex; gap: 2px; margin-left: 10px; }
.nb-shapes:empty { display: none; }
.nb-sub-right { margin-left: auto; display:flex; align-items:center; gap: 10px; }
.nb-lbl { display:inline-flex; align-items:center; gap: 5px; font-size: 12px; opacity: .85; }
.nb-lbl select { font: inherit; color: var(--fg); background: transparent; border: 1px solid var(--border); border-radius: 7px; padding: 2px 4px; }
.nb-check input { margin: 0; }
.nb-pageinfo { font-size: 12px; opacity: .7; font-variant-numeric: tabular-nums; }
.nb-body { flex: 1 1 auto; display: flex; min-height: 0; }
.nb-thumbs { width: 112px; flex: none; overflow-y: auto; border-right: 1px solid var(--border); padding: 8px; display:flex; flex-direction: column; gap: 8px; background: color-mix(in srgb, var(--bg) 80%, transparent); }
.nb-thumb { position: relative; cursor: pointer; border-radius: 6px; border: 2px solid transparent; padding: 2px; }
.nb-thumb canvas { display:block; width: 90px; height: 126px; border-radius: 3px; box-shadow: 0 1px 3px rgba(0,0,0,.25); background: #fff; }
.nb-thumb.cur { border-color: var(--accent); }
.nb-thumb span { position:absolute; right: 6px; bottom: 6px; font-size: 10px; background: rgba(0,0,0,.55); color:#fff; padding: 1px 5px; border-radius: 8px; }
.nb-thumb .nb-tdel { position:absolute; left: 6px; top: 6px; width: 18px; height: 18px; border-radius: 50%; border: 0; background: rgba(0,0,0,.55); color: #fff; font-size: 11px; line-height: 18px; cursor:pointer; display:none; padding:0; }
.nb-thumb:hover .nb-tdel { display:block; }
.nb-scroll { flex: 1 1 auto; overflow: auto; background: #d9dce3; padding: 18px; position: relative; }
.nb-pages { display:flex; flex-direction: column; align-items: center; gap: 18px; min-height: 100%; }
.nb-page { position: relative; background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,.25); flex: none; touch-action: pan-x pan-y pinch-zoom; cursor: crosshair; }
.nb-page.finger { touch-action: none; }
.nb-page.hand { cursor: grab; }
.nb-page.text { cursor: text; }
.nb-page.lasso { cursor: cell; }
.nb-page canvas { position:absolute; left:0; top:0; display:block; }
.nb-page .live { pointer-events: none; }
.nb-page .pnum { position:absolute; right: 8px; bottom: 6px; font-size: 11px; color: rgba(0,0,0,.4); pointer-events: none; }
.nb-ta { position:absolute; border: 1px dashed var(--accent); background: rgba(255,255,255,.85); font-family: Inter, sans-serif; line-height: 1.3; padding: 2px 4px; resize: both; min-width: 160px; min-height: 36px; outline: none; border-radius: 4px; z-index: 5; color: inherit; }
@media (max-width: 760px) {
  .nb-thumbs { display: none; }
  .nb-course { display: none; }
}
"""

JS = r"""
const STATES = new Map();
const W = 1000, H = 1400;
const PEN_COLORS = ['#000000','#3f3f46','#9ca3af','#dc2626','#ea580c','#ca8a04','#16a34a','#0d9488','#2563eb','#4f46e5','#9333ea','#db2777'];
const HL_COLORS = ['#fde047','#86efac','#93c5fd','#f9a8d4','#fdba74','#c4b5fd'];
const WIDTHS = { pen: [2, 3.5, 6], hl: [14, 22, 32], eraser: [10, 20, 36], text: [16, 22, 30], shape: [2, 3.5, 6] };
const PAPER_BG = { white: '#ffffff', cream: '#fdf6e3', dark: '#1f2937' };

const ICONS = {
  pen: '<svg viewBox="0 0 24 24"><path d="m3 21 2.5-.6 12.6-12.6a2 2 0 0 0 0-2.8l-1.1-1.1a2 2 0 0 0-2.8 0L3.6 16.5z"/><path d="m13 6 5 5"/></svg>',
  hl: '<svg viewBox="0 0 24 24"><path d="M9 11 4 16l2 2 1 3h3l2-2 5-5z"/><path d="m14 6 4 4 2-2-4-4z"/><path d="m9 11 4-4 4 4-4 4z"/></svg>',
  eraser: '<svg viewBox="0 0 24 24"><path d="m7 21-4-4a2 2 0 0 1 0-2.8L13.2 4a2 2 0 0 1 2.8 0l5 5a2 2 0 0 1 0 2.8L13 20H7z"/><path d="M6 11l7 7"/></svg>',
  lasso: '<svg viewBox="0 0 24 24"><path d="M7 20c-1-1-1-3 1-4 1 0 2 0 3-1"/><path d="M12 15c5 0 9-2.5 9-5.5S17 4 12 4 3 6.5 3 9.5c0 1.6 1 3 2.8 4"/><path d="M6 20c0-2 1-4 2-6"/></svg>',
  text: '<svg viewBox="0 0 24 24"><path d="M5 6V4h14v2M12 4v16M9 20h6"/></svg>',
  shape: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="8" height="8" rx="1.5"/><circle cx="16.5" cy="16.5" r="4.5"/><path d="M3 21 11 13"/></svg>',
  hand: '<svg viewBox="0 0 24 24"><path d="M18 11V6a2 2 0 0 0-4 0v1M14 10V4a2 2 0 0 0-4 0v2M10 10V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 0 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.9-5.6-2.3L3.6 14.7a2 2 0 0 1 3.3-2.2L8 14"/></svg>',
  line: '<svg viewBox="0 0 24 24"><path d="M4 20 20 4"/></svg>',
  arrow: '<svg viewBox="0 0 24 24"><path d="M4 20 20 4M11 4h9v9"/></svg>',
  rect: '<svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="14" rx="2"/></svg>',
  ellipse: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="12" rx="9" ry="7"/></svg>',
};
const TOOLS = [
  ['pen', 'Pen (P)'], ['hl', 'Highlighter (H)'], ['eraser', 'Eraser (E)'], ['lasso', 'Lasso select (L)'],
  ['text', 'Text (T)'], ['shape', 'Shapes (S)'], ['hand', 'Scroll with the pointer (V)'],
];

export default function (component) {
  const { data, setStateValue, parentElement, key } = component;
  const root = parentElement.querySelector('.nb');
  if (!root || !data) return;

  let S = root.__S;
  if (S && S.root === root && root.isConnected) {
    // Same DOM, called again after a rerun (an autosave, usually): nothing
    // to rebuild. Streamlit may have run our cleanup in between, so make
    // sure the document-level listeners are back.
    S.setStateValue = setStateValue;
    S.savedSeq = Math.max(S.savedSeq || 0, data.savedSeq || 0);
    if (!S.globalAttached) attachGlobal(S);
  } else {
    S = STATES.get(key);
    if (!S || S.noteId !== data.noteId) {
      S = makeState(data);
      STATES.set(key, S);
    } else {
      // The DOM was rebuilt but our state survived: keep whatever is newer,
      // and let go of the listeners that point at the old elements.
      S.setStateValue = setStateValue;
      if (S.globalAttached) detachGlobal(S);
      if (data.doc && (data.doc.seq || 0) > (S.doc.seq || 0)) S.doc = clone(data.doc);
      S.selection = null; S.drawing = null; S.touches = new Map(); S.pinch = null;
    }
    root.__S = S;
    S.root = root;
    S.setStateValue = setStateValue;
    S.savedSeq = Math.max(S.savedSeq || 0, data.savedSeq || 0);
    buildUI(S);
    attachGlobal(S);
    requestAnimationFrame(() => {
      if (!S.userZoomed) fitWidth(S); else setZoom(S, S.zoom);
      const sc = S.root.querySelector('.nb-scroll');
      if (sc && S.scrollTop) sc.scrollTop = S.scrollTop;
    });
  }
  S.meta = { title: data.title || '', course: data.course || '', color: data.color || '' };
  updateHeader(S);
  updateStatus(S);
  return () => { detachGlobal(S); };
}

// ---------------------------------------------------------------- state ----

function clone(o) { return JSON.parse(JSON.stringify(o)); }

function makeState(data) {
  const doc = data.doc && data.doc.pages && data.doc.pages.length ? clone(data.doc) : { v: 1, seq: 0, paper: 'lined', paperColor: 'white', pages: [{ items: [] }] };
  doc.seq = doc.seq || 0;
  return {
    noteId: data.noteId, doc, tool: 'pen', shapeKind: 'rect',
    color: { pen: '#000000', hl: '#fde047', text: '#000000', shape: '#000000' },
    widthIdx: { pen: 1, hl: 1, eraser: 1, text: 1, shape: 1 },
    zoom: 1, cur: 0, fingerDraws: false, dirty: false, sentSeq: 0, savedSeq: 0,
    undo: [], redo: [], drawing: null, selection: null, pinch: null, touches: new Map(),
    pageEls: [], thumbEls: [], thumbT: null, saveT: null, focused: false, globalAttached: false,
  };
}

function markDirty(S) {
  S.dirty = true;
  S.doc.seq = (S.doc.seq || 0) + 1;
  updateStatus(S);
  clearTimeout(S.saveT);
  S.saveT = setTimeout(() => save(S), 1500);
  scheduleThumb(S);
}

function save(S) {
  clearTimeout(S.saveT);
  if (!S.dirty) return;
  S.dirty = false;
  S.sentSeq = S.doc.seq;
  updateStatus(S);
  try { S.setStateValue('doc', clone(S.doc)); } catch (e) { S.dirty = true; updateStatus(S); }
}

function updateStatus(S) {
  const el = S.root.querySelector('.nb-status');
  if (!el) return;
  el.classList.remove('dirty', 'saving');
  if (S.dirty) { el.textContent = 'Unsaved'; el.classList.add('dirty'); }
  else if (S.sentSeq > (S.savedSeq || 0)) { el.textContent = 'Saving…'; el.classList.add('saving'); }
  else el.textContent = 'Saved';
}

function updateHeader(S) {
  S.root.querySelector('.nb-name').textContent = S.meta.title;
  S.root.querySelector('.nb-course').textContent = S.meta.course ? S.meta.course + ' ·' : '';
  S.root.querySelector('.nb-course-dot').style.background = S.meta.color || 'var(--accent)';
}

// ------------------------------------------------------------- building ----

function buildUI(S) {
  const r = S.root;
  const tools = r.querySelector('.nb-tools');
  tools.innerHTML = '';
  for (const [t, title] of TOOLS) {
    const b = document.createElement('button');
    b.className = 'nb-tb'; b.dataset.tool = t; b.title = title; b.innerHTML = ICONS[t];
    if (t === 'pen' || t === 'hl' || t === 'text' || t === 'shape') {
      const c = document.createElement('i'); c.className = 'nb-tcolor'; b.appendChild(c);
    }
    b.addEventListener('click', () => setTool(S, t));
    tools.appendChild(b);
  }
  r.querySelectorAll('.nb-ib[data-act]').forEach(b => b.addEventListener('click', () => action(S, b.dataset.act)));
  const paper = r.querySelector('.nb-paper'); paper.value = S.doc.paper || 'lined';
  paper.addEventListener('change', () => { S.doc.paper = paper.value; applyPaper(S); markDirty(S); });
  const pc = r.querySelector('.nb-pcolor'); pc.value = S.doc.paperColor || 'white';
  pc.addEventListener('change', () => { S.doc.paperColor = pc.value; applyPaper(S); renderAll(S); markDirty(S); });
  const finger = r.querySelector('.nb-finger'); finger.checked = S.fingerDraws;
  finger.addEventListener('change', () => { S.fingerDraws = finger.checked; S.pageEls.forEach(p => p.classList.toggle('finger', S.fingerDraws)); });
  const scroll = r.querySelector('.nb-scroll');
  scroll.addEventListener('scroll', () => { S.scrollTop = scroll.scrollTop; trackCurrent(S); }, { passive: true });
  scroll.addEventListener('wheel', (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    S.userZoomed = true;
    setZoom(S, S.zoom * (e.deltaY < 0 ? 1.1 : 0.9), e);
  }, { passive: false });
  r.addEventListener('pointerdown', () => { S.focused = true; }, true);
  buildPages(S);
  setTool(S, S.tool);
  updatePageInfo(S);
}

function buildPages(S) {
  const holder = S.root.querySelector('.nb-pages');
  holder.innerHTML = '';
  S.pageEls = [];
  S.doc.pages.forEach((_, i) => holder.appendChild(makePageEl(S, i)));
  buildThumbs(S);
  applyPaper(S);
  renderAll(S);
}

function makePageEl(S, idx) {
  const el = document.createElement('div');
  el.className = 'nb-page'; el.dataset.idx = idx;
  if (S.fingerDraws) el.classList.add('finger');
  const ink = document.createElement('canvas'); ink.className = 'ink';
  const live = document.createElement('canvas'); live.className = 'live';
  const num = document.createElement('div'); num.className = 'pnum'; num.textContent = idx + 1;
  el.appendChild(ink); el.appendChild(live); el.appendChild(num);
  el.addEventListener('pointerdown', (e) => onDown(S, el, e));
  el.addEventListener('pointermove', (e) => onMove(S, el, e));
  el.addEventListener('pointerup', (e) => onUp(S, el, e));
  el.addEventListener('pointercancel', (e) => onUp(S, el, e, true));
  el.addEventListener('dblclick', (e) => onDbl(S, el, e));
  el.addEventListener('contextmenu', (e) => e.preventDefault());
  S.pageEls[idx] = el;
  sizePage(S, el);
  return el;
}

function sizePage(S, el) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(W * S.zoom), h = Math.round(H * S.zoom);
  el.style.width = w + 'px'; el.style.height = h + 'px';
  for (const c of el.querySelectorAll('canvas')) {
    c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    c.style.width = w + 'px'; c.style.height = h + 'px';
  }
}

function buildThumbs(S) {
  const holder = S.root.querySelector('.nb-thumbs');
  holder.innerHTML = '';
  S.thumbEls = [];
  S.doc.pages.forEach((_, i) => {
    const t = document.createElement('div'); t.className = 'nb-thumb' + (i === S.cur ? ' cur' : '');
    const c = document.createElement('canvas'); c.width = 180; c.height = 252;
    const n = document.createElement('span'); n.textContent = i + 1;
    const d = document.createElement('button'); d.className = 'nb-tdel'; d.textContent = '×'; d.title = 'Delete this page';
    d.addEventListener('click', (e) => { e.stopPropagation(); deletePage(S, i); });
    t.appendChild(c); t.appendChild(n); t.appendChild(d);
    t.addEventListener('click', () => scrollToPage(S, i));
    holder.appendChild(t);
    S.thumbEls[i] = t;
  });
  renderThumbs(S);
}

// ----------------------------------------------------------- tool state ----

function famOf(tool) { return tool === 'shape' ? 'shape' : tool; }

function setTool(S, t) {
  S.tool = t;
  if (t !== 'lasso') clearSelection(S);
  S.root.querySelectorAll('.nb-tb').forEach(b => b.classList.toggle('active', b.dataset.tool === t));
  S.pageEls.forEach(p => { p.classList.toggle('hand', t === 'hand'); p.classList.toggle('text', t === 'text'); p.classList.toggle('lasso', t === 'lasso'); });
  buildSub(S);
}

function buildSub(S) {
  const sw = S.root.querySelector('.nb-swatches'); sw.innerHTML = '';
  const wd = S.root.querySelector('.nb-widths'); wd.innerHTML = '';
  const sh = S.root.querySelector('.nb-shapes'); sh.innerHTML = '';
  const fam = famOf(S.tool);
  if (['pen', 'hl', 'text', 'shape'].includes(fam)) {
    const colors = fam === 'hl' ? HL_COLORS : PEN_COLORS;
    for (const c of colors) {
      const b = document.createElement('button'); b.className = 'nb-sw' + (S.color[fam] === c ? ' active' : '');
      b.style.background = c; b.title = c;
      b.addEventListener('click', () => { S.color[fam] = c; buildSub(S); });
      sw.appendChild(b);
    }
    const custom = document.createElement('label'); custom.className = 'nb-sw custom'; custom.title = 'Any colour';
    const inp = document.createElement('input'); inp.type = 'color'; inp.value = S.color[fam];
    inp.addEventListener('input', () => { S.color[fam] = inp.value; S.root.querySelectorAll('.nb-sw').forEach(x => x.classList.remove('active')); updateToolColors(S); });
    custom.appendChild(inp); sw.appendChild(custom);
  }
  if (WIDTHS[fam]) {
    WIDTHS[fam].forEach((w, i) => {
      const b = document.createElement('button'); b.className = 'nb-wd' + (S.widthIdx[fam] === i ? ' active' : '');
      b.title = fam === 'text' ? w + ' px' : (['Thin', 'Medium', 'Thick'][i]);
      const dot = document.createElement('i'); const px = fam === 'text' ? [6, 9, 12][i] : Math.min(4 + i * 4, 16);
      dot.style.width = px + 'px'; dot.style.height = px + 'px';
      b.appendChild(dot);
      b.addEventListener('click', () => { S.widthIdx[fam] = i; buildSub(S); });
      wd.appendChild(b);
    });
  }
  if (fam === 'shape') {
    for (const k of ['line', 'arrow', 'rect', 'ellipse']) {
      const b = document.createElement('button'); b.className = 'nb-tb' + (S.shapeKind === k ? ' active' : ''); b.innerHTML = ICONS[k]; b.title = k;
      b.addEventListener('click', () => { S.shapeKind = k; buildSub(S); });
      sh.appendChild(b);
    }
  }
  if (S.tool === 'lasso' && S.selection) {
    const del = document.createElement('button'); del.className = 'nb-tb'; del.title = 'Delete selection (Del)';
    del.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';
    del.addEventListener('click', () => deleteSelection(S));
    const dup = document.createElement('button'); dup.className = 'nb-tb'; dup.title = 'Duplicate selection';
    dup.innerHTML = '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
    dup.addEventListener('click', () => duplicateSelection(S));
    sh.appendChild(del); sh.appendChild(dup);
  }
  updateToolColors(S);
}

function updateToolColors(S) {
  S.root.querySelectorAll('.nb-tb[data-tool]').forEach(b => {
    const c = b.querySelector('.nb-tcolor'); if (c) c.style.background = S.color[famOf(b.dataset.tool)] || '#000';
  });
}

function curWidth(S, fam) { return WIDTHS[fam][S.widthIdx[fam]]; }

// -------------------------------------------------------------- actions ----

function action(S, act) {
  if (act === 'undo') undo(S);
  else if (act === 'redo') redo(S);
  else if (act === 'zoomin') { S.userZoomed = true; setZoom(S, S.zoom * 1.2); }
  else if (act === 'zoomout') { S.userZoomed = true; setZoom(S, S.zoom / 1.2); }
  else if (act === 'fit') { S.userZoomed = false; fitWidth(S); }
  else if (act === 'addpage') addPage(S);
  else if (act === 'export') exportPage(S, S.cur);
  else if (act === 'save') { S.dirty = S.dirty || S.doc.seq > S.sentSeq; if (!S.dirty) { S.doc.seq++; S.dirty = true; } save(S); }
}

function pushUndo(S, idx) {
  S.undo.push({ idx, items: JSON.stringify(S.doc.pages[idx].items) });
  if (S.undo.length > 60) S.undo.shift();
  S.redo = [];
}

function undo(S) {
  const u = S.undo.pop(); if (!u) return;
  S.redo.push({ idx: u.idx, items: JSON.stringify(S.doc.pages[u.idx].items) });
  S.doc.pages[u.idx].items = JSON.parse(u.items);
  clearSelection(S); renderPage(S, u.idx); markDirty(S);
}

function redo(S) {
  const r = S.redo.pop(); if (!r) return;
  S.undo.push({ idx: r.idx, items: JSON.stringify(S.doc.pages[r.idx].items) });
  S.doc.pages[r.idx].items = JSON.parse(r.items);
  clearSelection(S); renderPage(S, r.idx); markDirty(S);
}

function addPage(S) {
  S.doc.pages.push({ items: [] });
  const holder = S.root.querySelector('.nb-pages');
  holder.appendChild(makePageEl(S, S.doc.pages.length - 1));
  applyPaper(S); renderPage(S, S.doc.pages.length - 1);
  buildThumbs(S); updatePageInfo(S); markDirty(S);
  scrollToPage(S, S.doc.pages.length - 1);
}

function deletePage(S, idx) {
  if (S.doc.pages.length <= 1) { clearPage(S, idx); return; }
  if (!window.confirm('Delete page ' + (idx + 1) + '? This cannot be undone.')) return;
  S.doc.pages.splice(idx, 1);
  S.undo = S.undo.filter(u => u.idx !== idx).map(u => ({ idx: u.idx > idx ? u.idx - 1 : u.idx, items: u.items }));
  S.redo = [];
  S.cur = Math.min(S.cur, S.doc.pages.length - 1);
  clearSelection(S); buildPages(S); updatePageInfo(S); markDirty(S);
}

function clearPage(S, idx) {
  if (!S.doc.pages[idx].items.length) return;
  if (!window.confirm('Clear everything on page ' + (idx + 1) + '?')) return;
  pushUndo(S, idx); S.doc.pages[idx].items = []; renderPage(S, idx); markDirty(S);
}

function setZoom(S, z, ev) {
  z = Math.max(0.35, Math.min(3, z));
  const scroll = S.root.querySelector('.nb-scroll');
  // keep the point under the cursor (or the centre) fixed
  const rect = scroll.getBoundingClientRect();
  const cx = ev ? ev.clientX - rect.left : rect.width / 2, cy = ev ? ev.clientY - rect.top : rect.height / 2;
  const ox = (scroll.scrollLeft + cx) / S.zoom, oy = (scroll.scrollTop + cy) / S.zoom;
  S.zoom = z;
  S.pageEls.forEach(p => sizePage(S, p));
  applyPaper(S); renderAll(S);
  scroll.scrollLeft = ox * z - cx; scroll.scrollTop = oy * z - cy;
  S.root.querySelector('.nb-zoom').textContent = Math.round(z * 100) + '%';
  relayoutTextareas(S);
}

function fitWidth(S) {
  const scroll = S.root.querySelector('.nb-scroll');
  const avail = scroll.clientWidth - 40;
  if (avail > 50) setZoom(S, avail / W);
}

function scrollToPage(S, idx) {
  const el = S.pageEls[idx]; if (!el) return;
  const scroll = S.root.querySelector('.nb-scroll');
  scroll.scrollTo({ top: el.offsetTop - 18, behavior: 'smooth' });
  S.cur = idx; markCurrent(S);
}

function trackCurrent(S) {
  const scroll = S.root.querySelector('.nb-scroll');
  const mid = scroll.scrollTop + scroll.clientHeight / 2;
  let best = 0, bd = Infinity;
  S.pageEls.forEach((p, i) => { const d = Math.abs(p.offsetTop + p.offsetHeight / 2 - mid); if (d < bd) { bd = d; best = i; } });
  if (best !== S.cur) { S.cur = best; markCurrent(S); }
}

function markCurrent(S) {
  S.thumbEls.forEach((t, i) => t.classList.toggle('cur', i === S.cur));
  updatePageInfo(S);
}

function updatePageInfo(S) {
  S.root.querySelector('.nb-pageinfo').textContent = 'Page ' + (S.cur + 1) + ' of ' + S.doc.pages.length;
}

// ---------------------------------------------------------------- paper ----

function paperCSS(paper, color, zoom) {
  const bg = PAPER_BG[color] || '#fff';
  const dark = color === 'dark';
  const line = dark ? 'rgba(255,255,255,.14)' : 'rgba(37,99,235,.20)';
  const dot = dark ? 'rgba(255,255,255,.28)' : 'rgba(30,41,59,.30)';
  const red = 'rgba(239,68,68,.35)';
  const gap = 32 * zoom, top = 88 * zoom, left = 96 * zoom;
  const layers = [], sizes = [], pos = [];
  const hline = `repeating-linear-gradient(to bottom, transparent 0, transparent ${gap - 1}px, ${line} ${gap - 1}px, ${line} ${gap}px)`;
  if (paper === 'lined' || paper === 'cornell') {
    layers.push(`linear-gradient(to right, transparent ${left - 1}px, ${red} ${left - 1}px, ${red} ${left}px, transparent ${left}px)`); sizes.push('100% 100%'); pos.push('0 0');
    layers.push(hline); sizes.push(`100% ${gap}px`); pos.push(`0 ${top}px`);
  }
  if (paper === 'cornell') {
    const cue = 260 * zoom, foot = (H - 300) * zoom;
    layers.push(`linear-gradient(to right, transparent ${cue - 1}px, ${line} ${cue - 1}px, ${line} ${cue + 1}px, transparent ${cue + 1}px)`); sizes.push('100% 100%'); pos.push('0 0');
    layers.push(`linear-gradient(to bottom, transparent ${foot - 1}px, ${line} ${foot - 1}px, ${line} ${foot + 1}px, transparent ${foot + 1}px)`); sizes.push('100% 100%'); pos.push('0 0');
  }
  if (paper === 'grid') {
    layers.push(hline); sizes.push(`100% ${gap}px`); pos.push('0 0');
    layers.push(`repeating-linear-gradient(to right, transparent 0, transparent ${gap - 1}px, ${line} ${gap - 1}px, ${line} ${gap}px)`); sizes.push(`${gap}px 100%`); pos.push('0 0');
  }
  if (paper === 'dotted') {
    layers.push(`radial-gradient(circle, ${dot} ${1.1 * zoom}px, transparent ${1.6 * zoom}px)`); sizes.push(`${gap}px ${gap}px`); pos.push(`${gap / 2}px ${gap / 2}px`);
  }
  return { bg, image: layers.join(','), size: sizes.join(','), pos: pos.join(',') };
}

function applyPaper(S) {
  const p = paperCSS(S.doc.paper || 'lined', S.doc.paperColor || 'white', S.zoom);
  for (const el of S.pageEls) {
    el.style.background = p.bg;
    el.style.backgroundImage = p.image; el.style.backgroundSize = p.size; el.style.backgroundPosition = p.pos;
    el.style.backgroundRepeat = p.image.includes('radial') || p.image.includes('repeating') ? 'repeat' : 'no-repeat';
  }
  const dark = (S.doc.paperColor === 'dark');
  if (dark && S.color.pen === '#000000') { S.color.pen = '#f3f4f6'; S.color.text = '#f3f4f6'; S.color.shape = '#f3f4f6'; updateToolColors(S); }
  if (!dark && S.color.pen === '#f3f4f6') { S.color.pen = '#000000'; S.color.text = '#000000'; S.color.shape = '#000000'; updateToolColors(S); }
}

// ------------------------------------------------------------ rendering ----

function ctxFor(S, canvas) {
  const dpr = window.devicePixelRatio || 1;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(S.zoom * dpr, 0, 0, S.zoom * dpr, 0, 0);
  return ctx;
}

function renderAll(S) { S.doc.pages.forEach((_, i) => renderPage(S, i)); scheduleThumb(S); }

function renderPage(S, idx) {
  const el = S.pageEls[idx]; if (!el) return;
  const ink = el.querySelector('.ink');
  const ctx = ctxFor(S, ink);
  ctx.clearRect(0, 0, W, H);
  for (const it of S.doc.pages[idx].items) drawItem(ctx, it);
  drawSelection(S, idx);
  scheduleThumb(S);
}

function drawItem(ctx, it) {
  if (it.t === 's') drawStroke(ctx, it);
  else if (it.t === 'x') drawText(ctx, it);
  else if (it.t === 'g') drawShape(ctx, it);
}

function drawStroke(ctx, s, liveFrom) {
  const p = s.p; if (!p || !p.length) return;
  ctx.save();
  ctx.strokeStyle = s.c; ctx.fillStyle = s.c; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  if (s.tool === 'hl') { ctx.globalAlpha = 0.38; ctx.globalCompositeOperation = 'multiply'; ctx.lineCap = 'butt'; }
  const start = Math.max(1, liveFrom || 1);
  if (p.length === 1) {
    const r = (s.tool === 'hl' ? s.w / 2 : s.w * (0.4 + 1.2 * (p[0][2] || 0.5)) / 2);
    ctx.beginPath(); ctx.arc(p[0][0], p[0][1], r, 0, Math.PI * 2); ctx.fill(); ctx.restore(); return;
  }
  if (s.tool === 'hl' || !s.v) {
    ctx.lineWidth = s.w;
    ctx.beginPath();
    if (start === 1) ctx.moveTo(p[0][0], p[0][1]); else ctx.moveTo((p[start - 2][0] + p[start - 1][0]) / 2, (p[start - 2][1] + p[start - 1][1]) / 2);
    for (let i = start; i < p.length; i++) {
      const mx = (p[i - 1][0] + p[i][0]) / 2, my = (p[i - 1][1] + p[i][1]) / 2;
      ctx.quadraticCurveTo(p[i - 1][0], p[i - 1][1], mx, my);
    }
    const last = p[p.length - 1]; ctx.lineTo(last[0], last[1]);
    ctx.stroke();
  } else {
    for (let i = start; i < p.length; i++) {
      const pr = ((p[i - 1][2] || 0.5) + (p[i][2] || 0.5)) / 2;
      ctx.lineWidth = s.w * (0.35 + 1.3 * pr);
      ctx.beginPath();
      if (i === 1) ctx.moveTo(p[0][0], p[0][1]); else ctx.moveTo((p[i - 2][0] + p[i - 1][0]) / 2, (p[i - 2][1] + p[i - 1][1]) / 2);
      const mx = (p[i - 1][0] + p[i][0]) / 2, my = (p[i - 1][1] + p[i][1]) / 2;
      ctx.quadraticCurveTo(p[i - 1][0], p[i - 1][1], mx, my);
      ctx.stroke();
    }
  }
  ctx.restore();
}

function textLines(it) { return String(it.text || '').split('\n'); }

function drawText(ctx, it) {
  ctx.save();
  ctx.fillStyle = it.c; ctx.font = `${it.size}px Inter, -apple-system, "Segoe UI", sans-serif`; ctx.textBaseline = 'top';
  const lh = it.size * 1.3; let w = 0;
  textLines(it).forEach((ln, i) => { ctx.fillText(ln, it.x, it.y + i * lh); w = Math.max(w, ctx.measureText(ln).width); });
  it.bw = w; it.bh = lh * textLines(it).length;
  ctx.restore();
}

function drawShape(ctx, g) {
  ctx.save();
  ctx.strokeStyle = g.c; ctx.lineWidth = g.w; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  const x1 = g.x1, y1 = g.y1, x2 = g.x2, y2 = g.y2;
  ctx.beginPath();
  if (g.k === 'line' || g.k === 'arrow') { ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); }
  if (g.k === 'arrow') {
    const a = Math.atan2(y2 - y1, x2 - x1), L = 10 + g.w * 2.5;
    ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - L * Math.cos(a - 0.45), y2 - L * Math.sin(a - 0.45));
    ctx.moveTo(x2, y2); ctx.lineTo(x2 - L * Math.cos(a + 0.45), y2 - L * Math.sin(a + 0.45)); ctx.stroke();
  }
  if (g.k === 'rect') { ctx.rect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1)); ctx.stroke(); }
  if (g.k === 'ellipse') { ctx.ellipse((x1 + x2) / 2, (y1 + y2) / 2, Math.abs(x2 - x1) / 2, Math.abs(y2 - y1) / 2, 0, 0, Math.PI * 2); ctx.stroke(); }
  ctx.restore();
}

function scheduleThumb(S) {
  clearTimeout(S.thumbT);
  S.thumbT = setTimeout(() => renderThumbs(S), 350);
}

function renderThumbs(S) {
  S.doc.pages.forEach((pg, i) => {
    const t = S.thumbEls[i]; if (!t) return;
    const c = t.querySelector('canvas'); const ctx = c.getContext('2d');
    const sc = c.width / W;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = PAPER_BG[S.doc.paperColor] || '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    ctx.setTransform(sc, 0, 0, sc, 0, 0);
    for (const it of pg.items) drawItem(ctx, it);
  });
}

// ----------------------------------------------------------- selection ----

function clearSelection(S) {
  if (!S.selection) return;
  const idx = S.selection.idx; S.selection = null;
  const el = S.pageEls[idx]; if (el) ctxFor(S, el.querySelector('.live')).clearRect(0, 0, W, H);
  if (S.tool === 'lasso') buildSub(S);
}

function itemBounds(it) {
  if (it.t === 's') {
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const [x, y] of it.p) { if (x < x1) x1 = x; if (y < y1) y1 = y; if (x > x2) x2 = x; if (y > y2) y2 = y; }
    const pad = it.w / 2; return [x1 - pad, y1 - pad, x2 + pad, y2 + pad];
  }
  if (it.t === 'x') return [it.x, it.y, it.x + (it.bw || 100), it.y + (it.bh || it.size * 1.3)];
  return [Math.min(it.x1, it.x2), Math.min(it.y1, it.y2), Math.max(it.x1, it.x2), Math.max(it.y1, it.y2)];
}

function selectionBounds(S) {
  const items = S.doc.pages[S.selection.idx].items;
  let b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const i of S.selection.ids) { const q = itemBounds(items[i]); b = [Math.min(b[0], q[0]), Math.min(b[1], q[1]), Math.max(b[2], q[2]), Math.max(b[3], q[3])]; }
  return b;
}

function drawSelection(S, idx) {
  const el = S.pageEls[idx]; if (!el) return;
  const ctx = ctxFor(S, el.querySelector('.live')); ctx.clearRect(0, 0, W, H);
  if (!S.selection || S.selection.idx !== idx || !S.selection.ids.length) return;
  const b = selectionBounds(S);
  ctx.save(); ctx.setLineDash([6, 4]); ctx.strokeStyle = '#4f46e5'; ctx.lineWidth = 1.5 / S.zoom;
  ctx.strokeRect(b[0] - 6, b[1] - 6, b[2] - b[0] + 12, b[3] - b[1] + 12);
  ctx.fillStyle = 'rgba(79,70,229,.08)'; ctx.fillRect(b[0] - 6, b[1] - 6, b[2] - b[0] + 12, b[3] - b[1] + 12);
  ctx.restore();
}

function pointInPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

function selectByLasso(S, idx, poly) {
  if (poly.length < 3) { clearSelection(S); return; }
  const ids = [];
  S.doc.pages[idx].items.forEach((it, i) => {
    if (it.t === 's') {
      let n = 0; for (const [x, y] of it.p) if (pointInPoly(x, y, poly)) n++;
      if (n >= Math.max(1, it.p.length * 0.5)) ids.push(i);
    } else {
      const b = itemBounds(it); if (pointInPoly((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, poly)) ids.push(i);
    }
  });
  S.selection = ids.length ? { idx, ids } : null;
  drawSelection(S, idx); buildSub(S);
}

function translateItem(it, dx, dy) {
  if (it.t === 's') for (const p of it.p) { p[0] += dx; p[1] += dy; }
  else if (it.t === 'x') { it.x += dx; it.y += dy; }
  else { it.x1 += dx; it.y1 += dy; it.x2 += dx; it.y2 += dy; }
}

function deleteSelection(S) {
  if (!S.selection) return;
  const { idx, ids } = S.selection; pushUndo(S, idx);
  const kill = new Set(ids);
  S.doc.pages[idx].items = S.doc.pages[idx].items.filter((_, i) => !kill.has(i));
  S.selection = null; renderPage(S, idx); markDirty(S); buildSub(S);
}

function duplicateSelection(S) {
  if (!S.selection) return;
  const { idx, ids } = S.selection; pushUndo(S, idx);
  const items = S.doc.pages[idx].items; const added = [];
  for (const i of ids) { const c = clone(items[i]); translateItem(c, 24, 24); items.push(c); added.push(items.length - 1); }
  S.selection = { idx, ids: added }; renderPage(S, idx); markDirty(S);
}

// -------------------------------------------------------------- pointer ----

function toLocal(S, el, e) {
  const r = el.getBoundingClientRect();
  return [(e.clientX - r.left) / S.zoom, (e.clientY - r.top) / S.zoom];
}

function onDown(S, el, e) {
  S.focused = true;
  const idx = +el.dataset.idx;
  if (e.pointerType === 'touch') {
    S.touches.set(e.pointerId, e);
    if (S.touches.size === 2) {
      const [a, b] = [...S.touches.values()];
      S.pinch = { d0: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY), z0: S.zoom };
      if (S.drawing) { S.drawing = null; ctxFor(S, el.querySelector('.live')).clearRect(0, 0, W, H); drawSelection(S, idx); }
      return;
    }
    if (!S.fingerDraws && S.tool !== 'hand' && S.tool !== 'text') return; // finger scrolls, stylus writes
  }
  if (e.button !== 0 && e.pointerType === 'mouse') return;
  if (e.target.closest && e.target.closest('.nb-ta')) return;
  const [x, y] = toLocal(S, el, e);
  let tool = S.tool;
  if (e.pointerType === 'pen' && (e.buttons & 32 || e.button === 5)) tool = 'eraser'; // stylus eraser end
  if (S.cur !== idx) { S.cur = idx; markCurrent(S); }
  const scroll = S.root.querySelector('.nb-scroll');
  if (tool === 'hand') { S.drawing = { kind: 'hand', sx: e.clientX, sy: e.clientY, sl: scroll.scrollLeft, st: scroll.scrollTop, idx }; el.setPointerCapture(e.pointerId); return; }
  if (tool === 'text') { startText(S, el, idx, x, y); return; }
  el.setPointerCapture(e.pointerId);
  if (tool === 'lasso') {
    if (S.selection && S.selection.idx === idx) {
      const b = selectionBounds(S);
      if (x >= b[0] - 8 && x <= b[2] + 8 && y >= b[1] - 8 && y <= b[3] + 8) {
        pushUndo(S, idx); S.drawing = { kind: 'move', idx, lx: x, ly: y, moved: false }; return;
      }
    }
    clearSelection(S);
    S.drawing = { kind: 'lasso', idx, poly: [[x, y]] }; return;
  }
  if (tool === 'eraser') {
    S.drawing = { kind: 'erase', idx, r: curWidth(S, 'eraser') / 2, snap: JSON.stringify(S.doc.pages[idx].items), changed: false };
    eraseAt(S, idx, x, y); return;
  }
  if (tool === 'shape') {
    S.drawing = { kind: 'shape', idx, g: { t: 'g', k: S.shapeKind, x1: x, y1: y, x2: x, y2: y, c: S.color.shape, w: curWidth(S, 'shape') } }; return;
  }
  const fam = tool === 'hl' ? 'hl' : 'pen';
  const pr = e.pointerType === 'pen' ? (e.pressure || 0.5) : 0.5;
  S.drawing = { kind: 'stroke', idx, s: { t: 's', tool: fam, c: S.color[fam], w: curWidth(S, fam), p: [[x, y, pr]], v: e.pointerType === 'pen' }, drawn: 0 };
}

function onMove(S, el, e) {
  if (e.pointerType === 'touch' && S.touches.has(e.pointerId)) {
    S.touches.set(e.pointerId, e);
    if (S.pinch && S.touches.size === 2) {
      const [a, b] = [...S.touches.values()];
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      if (!S.pinchRaf) S.pinchRaf = requestAnimationFrame(() => { S.pinchRaf = null; setZoom(S, S.pinch.z0 * d / S.pinch.d0, { clientX: (a.clientX + b.clientX) / 2, clientY: (a.clientY + b.clientY) / 2 }); });
      return;
    }
  }
  const d = S.drawing; if (!d || d.idx !== +el.dataset.idx) return;
  if (d.kind === 'hand') {
    const scroll = S.root.querySelector('.nb-scroll');
    scroll.scrollLeft = d.sl - (e.clientX - d.sx); scroll.scrollTop = d.st - (e.clientY - d.sy); return;
  }
  const events = (e.getCoalescedEvents && e.getCoalescedEvents().length) ? e.getCoalescedEvents() : [e];
  if (d.kind === 'stroke') {
    for (const ev of events) {
      const [x, y] = toLocal(S, el, ev);
      const last = d.s.p[d.s.p.length - 1];
      if (Math.hypot(x - last[0], y - last[1]) < 0.7) continue;
      d.s.p.push([x, y, ev.pointerType === 'pen' ? (ev.pressure || 0.5) : 0.5]);
    }
    const ctx = ctxFor(S, el.querySelector('.live'));
    if (d.s.tool === 'hl') { ctx.clearRect(0, 0, W, H); drawStroke(ctx, d.s); }
    else { drawStroke(ctx, d.s, d.drawn + 1); d.drawn = d.s.p.length - 1; }
  } else if (d.kind === 'erase') {
    for (const ev of events) { const [x, y] = toLocal(S, el, ev); eraseAt(S, d.idx, x, y); }
  } else if (d.kind === 'lasso') {
    const [x, y] = toLocal(S, el, e); d.poly.push([x, y]);
    const ctx = ctxFor(S, el.querySelector('.live')); ctx.clearRect(0, 0, W, H);
    ctx.save(); ctx.setLineDash([5, 4]); ctx.strokeStyle = '#4f46e5'; ctx.lineWidth = 1.5 / S.zoom; ctx.beginPath();
    d.poly.forEach(([px, py], i) => i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)); ctx.closePath(); ctx.stroke();
    ctx.fillStyle = 'rgba(79,70,229,.06)'; ctx.fill(); ctx.restore();
  } else if (d.kind === 'move') {
    const [x, y] = toLocal(S, el, e); const dx = x - d.lx, dy = y - d.ly;
    if (!dx && !dy) return;
    d.lx = x; d.ly = y; d.moved = true;
    const items = S.doc.pages[d.idx].items;
    for (const i of S.selection.ids) translateItem(items[i], dx, dy);
    renderPage(S, d.idx);
  } else if (d.kind === 'shape') {
    const [x, y] = toLocal(S, el, e);
    if (e.shiftKey) { const dx = x - d.g.x1, dy = y - d.g.y1, m = Math.max(Math.abs(dx), Math.abs(dy)); d.g.x2 = d.g.x1 + Math.sign(dx) * m; d.g.y2 = d.g.y1 + Math.sign(dy) * m; }
    else { d.g.x2 = x; d.g.y2 = y; }
    const ctx = ctxFor(S, el.querySelector('.live')); ctx.clearRect(0, 0, W, H); drawShape(ctx, d.g);
  }
}

function onUp(S, el, e, cancelled) {
  if (e.pointerType === 'touch') {
    S.touches.delete(e.pointerId);
    if (S.touches.size < 2) S.pinch = null;
  }
  const d = S.drawing; if (!d || d.idx !== +el.dataset.idx) return;
  S.drawing = null;
  try { el.releasePointerCapture(e.pointerId); } catch (_) {}
  const live = ctxFor(S, el.querySelector('.live'));
  if (d.kind === 'stroke') {
    live.clearRect(0, 0, W, H);
    if (!cancelled) { pushUndo(S, d.idx); S.doc.pages[d.idx].items.push(d.s); renderPage(S, d.idx); markDirty(S); }
  } else if (d.kind === 'erase') {
    if (d.changed) { S.undo.push({ idx: d.idx, items: d.snap }); if (S.undo.length > 60) S.undo.shift(); S.redo = []; markDirty(S); }
  } else if (d.kind === 'lasso') {
    live.clearRect(0, 0, W, H); selectByLasso(S, d.idx, d.poly);
  } else if (d.kind === 'move') {
    if (d.moved) markDirty(S); else S.undo.pop();
    drawSelection(S, d.idx);
  } else if (d.kind === 'shape') {
    live.clearRect(0, 0, W, H);
    if (!cancelled && (Math.abs(d.g.x2 - d.g.x1) > 2 || Math.abs(d.g.y2 - d.g.y1) > 2)) {
      pushUndo(S, d.idx); S.doc.pages[d.idx].items.push(d.g); renderPage(S, d.idx); markDirty(S);
    }
  }
}

function onDbl(S, el, e) {
  if (S.tool !== 'lasso' && S.tool !== 'pen') return;
  const idx = +el.dataset.idx; const [x, y] = toLocal(S, el, e);
  const items = S.doc.pages[idx].items;
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    if (it.t === 'x') { const b = itemBounds(it); if (x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3]) { editText(S, el, idx, i); return; } }
  }
}

function hitItem(it, x, y, r) {
  if (it.t === 's') {
    const rr = r + it.w / 2;
    for (let i = 0; i < it.p.length; i++) {
      const p = it.p[i]; if (Math.hypot(p[0] - x, p[1] - y) <= rr) return true;
      if (i) { const q = it.p[i - 1]; const mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2; if (Math.hypot(mx - x, my - y) <= rr) return true; }
    }
    return false;
  }
  if (it.t === 'x') { const b = itemBounds(it); return x >= b[0] - r && x <= b[2] + r && y >= b[1] - r && y <= b[3] + r; }
  const n = 32, rr = r + it.w;
  for (let i = 0; i <= n; i++) {
    const t = i / n; let px, py;
    if (it.k === 'line' || it.k === 'arrow') { px = it.x1 + (it.x2 - it.x1) * t; py = it.y1 + (it.y2 - it.y1) * t; }
    else if (it.k === 'ellipse') { const a = t * Math.PI * 2; px = (it.x1 + it.x2) / 2 + Math.cos(a) * Math.abs(it.x2 - it.x1) / 2; py = (it.y1 + it.y2) / 2 + Math.sin(a) * Math.abs(it.y2 - it.y1) / 2; }
    else { const per = t * 4, s = Math.floor(per), f = per - s; const xs = [it.x1, it.x2, it.x2, it.x1, it.x1], ys = [it.y1, it.y1, it.y2, it.y2, it.y1]; px = xs[s] + (xs[s + 1] - xs[s]) * f; py = ys[s] + (ys[s + 1] - ys[s]) * f; }
    if (Math.hypot(px - x, py - y) <= rr) return true;
  }
  return false;
}

function eraseAt(S, idx, x, y) {
  const d = S.drawing; const items = S.doc.pages[idx].items;
  const keep = items.filter(it => !hitItem(it, x, y, d.r));
  if (keep.length !== items.length) { S.doc.pages[idx].items = keep; d.changed = true; renderPage(S, idx); }
}

// ----------------------------------------------------------------- text ----

function startText(S, el, idx, x, y) {
  if (el.querySelector('.nb-ta')) { el.querySelector('.nb-ta').blur(); return; }
  const items = S.doc.pages[idx].items;
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    if (it.t === 'x') { const b = itemBounds(it); if (x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3]) { editText(S, el, idx, i); return; } }
  }
  openTextarea(S, el, idx, { x, y, size: curWidth(S, 'text'), c: S.color.text, text: '' }, null);
}

function editText(S, el, idx, i) {
  const it = S.doc.pages[idx].items[i];
  pushUndo(S, idx);
  S.doc.pages[idx].items.splice(i, 1); renderPage(S, idx);
  openTextarea(S, el, idx, clone(it), it);
}

function openTextarea(S, el, idx, it, original) {
  const ta = document.createElement('textarea');
  ta.className = 'nb-ta'; ta.value = it.text || ''; ta.placeholder = 'Type… click away to finish';
  ta.__it = it;
  el.appendChild(ta);
  placeTextarea(S, ta);
  let done = false;
  const commit = () => {
    if (done) return; done = true;
    const text = ta.value.replace(/\s+$/, '');
    ta.remove();
    if (text.trim()) {
      if (!original) pushUndo(S, idx);
      S.doc.pages[idx].items.push({ t: 'x', x: it.x, y: it.y, text, size: it.size, c: it.c });
      renderPage(S, idx); markDirty(S);
    } else if (original) { markDirty(S); }
  };
  ta.addEventListener('blur', commit);
  ta.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); ta.blur(); } e.stopPropagation(); });
  ta.addEventListener('pointerdown', (e) => e.stopPropagation());
  setTimeout(() => ta.focus(), 0);
}

function placeTextarea(S, ta) {
  const it = ta.__it;
  ta.style.left = (it.x * S.zoom - 5) + 'px'; ta.style.top = (it.y * S.zoom - 3) + 'px';
  ta.style.fontSize = (it.size * S.zoom) + 'px'; ta.style.color = it.c;
}

function relayoutTextareas(S) { S.root.querySelectorAll('.nb-ta').forEach(ta => placeTextarea(S, ta)); }

// --------------------------------------------------------------- export ----

function exportPage(S, idx) {
  const pg = S.doc.pages[idx]; if (!pg) return;
  const sc = 2, c = document.createElement('canvas'); c.width = W * sc; c.height = H * sc;
  const ctx = c.getContext('2d');
  ctx.fillStyle = PAPER_BG[S.doc.paperColor] || '#fff'; ctx.fillRect(0, 0, c.width, c.height);
  ctx.setTransform(sc, 0, 0, sc, 0, 0);
  const dark = S.doc.paperColor === 'dark';
  ctx.strokeStyle = dark ? 'rgba(255,255,255,.14)' : 'rgba(37,99,235,.20)'; ctx.lineWidth = 1;
  const paper = S.doc.paper;
  if (paper === 'lined' || paper === 'cornell') { for (let y = 88; y < H; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); } ctx.save(); ctx.strokeStyle = 'rgba(239,68,68,.35)'; ctx.beginPath(); ctx.moveTo(96, 0); ctx.lineTo(96, H); ctx.stroke(); ctx.restore(); }
  if (paper === 'cornell') { ctx.beginPath(); ctx.moveTo(260, 0); ctx.lineTo(260, H); ctx.moveTo(0, H - 300); ctx.lineTo(W, H - 300); ctx.stroke(); }
  if (paper === 'grid') { for (let y = 0; y < H; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); } for (let x = 0; x < W; x += 32) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); } }
  if (paper === 'dotted') { ctx.fillStyle = dark ? 'rgba(255,255,255,.28)' : 'rgba(30,41,59,.30)'; for (let y = 16; y < H; y += 32) for (let x = 16; x < W; x += 32) { ctx.beginPath(); ctx.arc(x, y, 1.2, 0, Math.PI * 2); ctx.fill(); } }
  for (const it of pg.items) drawItem(ctx, it);
  const a = document.createElement('a');
  a.href = c.toDataURL('image/png');
  a.download = (S.meta.title || 'notes').replace(/[^\w\- ]+/g, '').trim() + '-page' + (idx + 1) + '.png';
  document.body.appendChild(a); a.click(); a.remove();
}

// ------------------------------------------------------------- keyboard ----

function attachGlobal(S) {
  if (S.globalAttached) return;
  S.globalAttached = true;
  S._onKey = (e) => {
    if (!S.focused) return;
    const t = e.target; const tag = t && t.tagName ? t.tagName.toLowerCase() : '';
    if (tag === 'textarea' || tag === 'input' || tag === 'select' || (t && t.isContentEditable)) return;
    const k = e.key.toLowerCase(); const mod = e.ctrlKey || e.metaKey;
    if (mod && k === 'z') { e.preventDefault(); e.shiftKey ? redo(S) : undo(S); return; }
    if (mod && k === 'y') { e.preventDefault(); redo(S); return; }
    if (mod && k === 's') { e.preventDefault(); action(S, 'save'); return; }
    if (mod) return;
    if (k === 'z') { e.shiftKey ? redo(S) : undo(S); }
    else if (k === 'p') setTool(S, 'pen'); else if (k === 'h') setTool(S, 'hl'); else if (k === 'e') setTool(S, 'eraser');
    else if (k === 'l') setTool(S, 'lasso'); else if (k === 't') setTool(S, 'text'); else if (k === 's') setTool(S, 'shape'); else if (k === 'v') setTool(S, 'hand');
    else if (k === 'delete' || k === 'backspace') { if (S.selection) { e.preventDefault(); deleteSelection(S); } }
    else if (k === '+' || k === '=') setZoom(S, S.zoom * 1.2); else if (k === '-') setZoom(S, S.zoom / 1.2); else if (k === '0') fitWidth(S);
    else if (k === '[' || k === ']') { const f = famOf(S.tool); if (WIDTHS[f]) { S.widthIdx[f] = Math.max(0, Math.min(2, S.widthIdx[f] + (k === ']' ? 1 : -1))); buildSub(S); } }
    else if (k === 'escape') clearSelection(S);
  };
  S._onDocDown = (e) => { S.focused = !!(e.composedPath && e.composedPath().includes(S.root)); };
  S._onFlush = () => { if (S.dirty) save(S); };
  document.addEventListener('keydown', S._onKey);
  document.addEventListener('pointerdown', S._onDocDown, true);
  document.addEventListener('visibilitychange', S._onFlush);
  window.addEventListener('pagehide', S._onFlush);
  window.addEventListener('beforeunload', S._onFlush);
  S._ro = new ResizeObserver(() => { if (!S.userZoomed) fitWidth(S); });
  S._ro.observe(S.root.querySelector('.nb-scroll'));
}

function detachGlobal(S) {
  if (!S.globalAttached) return;
  S.globalAttached = false;
  if (S.dirty) save(S);
  document.removeEventListener('keydown', S._onKey);
  document.removeEventListener('pointerdown', S._onDocDown, true);
  document.removeEventListener('visibilitychange', S._onFlush);
  window.removeEventListener('pagehide', S._onFlush);
  window.removeEventListener('beforeunload', S._onFlush);
  if (S._ro) S._ro.disconnect();
}
"""

_editor = component("notability_canvas", html=HTML, css=CSS, js=JS, isolate_styles=True)


def mount(
    note_id: int,
    doc: dict,
    title: str,
    course: str = "",
    color: str = "",
    saved_seq: int = 0,
    height: int = 800,
    key: str | None = None,
):
    """Render the editor for one notebook. ``result.doc`` is the document the
    page last sent back, or ``None`` if it has not saved anything yet."""
    return _editor(
        key=key or f"nb_{int(note_id)}",
        data={
            "noteId": int(note_id),
            "title": title,
            "course": course,
            "color": color,
            "doc": doc,
            "savedSeq": int(saved_seq),
        },
        height=int(height),
        on_doc_change=lambda: None,
    )
