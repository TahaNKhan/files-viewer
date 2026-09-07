(() => {
  const $ = (s) => document.querySelector(s), state = { request: 0, direct: false };
  const api = (url) => fetch(url, { headers: { Accept: 'application/json' } });
  const fmt = (n) => n == null ? '—' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  const partsFor = (path) => path.split('/').filter(Boolean), encodedPath = (path) => partsFor(path).map(encodeURIComponent).join('/');
  function message(text, error = false) { $('#status').replaceChildren(); if (!text) return; const el = document.createElement('div'); el.className = error ? 'error' : 'notice'; el.textContent = text; $('#status').append(el); }
  function crumbs(parts) { const box = $('#breadcrumbs'); box.replaceChildren(); let url = ''; parts.forEach((part, i) => { url += '/' + encodeURIComponent(part); const a = document.createElement('a'); a.className = 'crumb'; a.href = url; a.textContent = part; box.append(a); if (i < parts.length - 1) box.append(' / '); }); }
  function link(entry) { const a = document.createElement('a'); a.href = entry.url; if (state.direct && entry.kind !== 'directory') a.search = '?direct'; a.textContent = (entry.kind === 'directory' ? '📁 ' : '') + entry.name; return a; }
  function applyMode() { document.body.classList.toggle('direct-mode', state.direct); }
  async function load(path, query = new URLSearchParams(location.search)) {
    const id = ++state.request; state.direct = query.has('direct') && !['0', 'false'].includes(query.get('direct')); applyMode();
    $('#viewer').hidden = true; $('#viewer').replaceChildren(); $('#listing').replaceChildren(); message('Loading…'); crumbs(partsFor(path));
    try {
      const r = await api('/api/list/' + encodedPath(path)); if (id !== state.request) return;
      if (r.ok) { const data = await r.json(); if (id !== state.request) return; const wrap = document.createElement('div'); wrap.className = 'listing'; if (!data.entries.length) { const e = document.createElement('div'); e.className = 'empty'; e.textContent = 'This directory is empty.'; wrap.append(e); } data.entries.forEach(entry => { const row = document.createElement('div'); row.className = 'row'; row.append(link(entry)); const size = document.createElement('span'); size.className = 'meta'; size.textContent = entry.kind === 'directory' ? 'Directory' : fmt(entry.size); const date = document.createElement('span'); date.className = 'meta modified'; date.textContent = entry.modified ? new Date(entry.modified * 1000).toLocaleString() : ''; row.append(size, date); wrap.append(row); }); $('#listing').replaceChildren(wrap); message(data.truncated ? 'Showing the first 2,000 visible entries.' : ''); return; }
      await showFile(path, id);
    } catch (_) { if (id === state.request) { $('#viewer').replaceChildren(); message('Could not load this path. Check your session and try again.', true); } }
  }
  async function showFile(path, id) {
    const r = await api('/api/file/' + encodedPath(path)); if (id !== state.request) return; if (!r.ok) { message('File could not be loaded.', true); return; }
    const kind = r.headers.get('content-type') || '', viewerKind = r.headers.get('x-viewer-kind') || '', fragment = document.createDocumentFragment(), box = $('#viewer');
    const title = document.createElement('h1'); title.className = 'file-title'; title.textContent = partsFor(path).pop(); if (!state.direct) fragment.append(title);
    if (viewerKind === 'markdown') { const md = document.createElement('div'); md.className = 'markdown markdown-body'; md.innerHTML = await r.text(); if (id !== state.request) return; fragment.append(md); }
    else if (kind.includes('text/html')) { const frame = document.createElement('iframe'); frame.sandbox = ''; frame.referrerPolicy = 'no-referrer'; frame.src = '/api/file/' + encodedPath(path); fragment.append(frame); }
    else if (kind.startsWith('image/')) { const img = document.createElement('img'); img.src = '/api/file/' + encodedPath(path); img.alt = title.textContent; fragment.append(img); }
    else if (kind === 'application/pdf') { const frame = document.createElement('iframe'); frame.src = '/api/file/' + encodedPath(path); frame.title = title.textContent; fragment.append(frame); }
    else if (kind.startsWith('text/')) { const pre = document.createElement('pre'); pre.textContent = await r.text(); if (id !== state.request) return; fragment.append(pre); }
    else { const a = document.createElement('a'); a.href = '/api/download/' + encodedPath(path); a.textContent = 'Download file'; fragment.append(a); }
    if (id !== state.request) return; box.className = state.direct ? 'viewer direct-viewer' : 'viewer'; box.replaceChildren(fragment); box.hidden = false; $('#listing').replaceChildren(); message('');
  }
  async function init() { try { const r = await api('/api/whoami'); if (r.ok) { const d = await r.json(); $('#identity').textContent = d.email || d.user || ''; const tree = $('#tree'); d.roots.forEach(root => { const a = document.createElement('a'); a.className = 'tree-link'; a.href = '/' + encodeURIComponent(root.name); a.textContent = root.label; tree.append(a); }); } } catch (_) {} const path = location.pathname.replace(/^\//, ''); load(path && !path.startsWith('api/') && !path.startsWith('static/') ? path : ''); }
  window.addEventListener('popstate', () => load(location.pathname.replace(/^\//, ''), new URLSearchParams(location.search)));
  $('#toggle').addEventListener('click', () => { const tree = $('#tree'), open = tree.style.display !== 'none'; tree.style.display = open ? 'none' : ''; $('#toggle').setAttribute('aria-expanded', String(!open)); });
  document.addEventListener('click', e => { const a = e.target.closest('a'); if (!a || a.target || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || new URL(a.href).origin !== location.origin || a.pathname.startsWith('/oauth2/') || a.searchParams.has('raw')) return; if (a.pathname.startsWith('/projects') || a.pathname.startsWith('/hermes')) { e.preventDefault(); history.pushState({}, '', a.href); load(location.pathname.replace(/^\//, ''), new URLSearchParams(location.search)); } });
  init();
})();
