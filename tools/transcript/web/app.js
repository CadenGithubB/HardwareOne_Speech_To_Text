import {TranscriptStore, turns, ordering, parseRecording} from './model.mjs';
const $ = id => document.getElementById(id);
const store = new TranscriptStore();
let selected = '', cursor = 0, following = true, connected = false, busy = false;
const annotations = new Map();
const textNodes = new Map();
function notify(text) { $('message').textContent = text; }
async function command(value) {
  try {
    const response = await fetch('/api/command', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:value})});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Command failed');
    notify('Command sent; waiting for P4 response.');
  } catch (error) { notify(error.message); }
}
function annotation(id) { if (!annotations.has(id)) annotations.set(id, {title:'', aliases:{}}); return annotations.get(id); }
function title(s) { return annotation(s.id).title || s.title || 'Untitled recording'; }
function info(s) {
  const m = s.metadata;
  const date = m.clockKnown && m.startedUtc ? m.startedUtc : 'Date unavailable';
  const order = m.bootDurable ? `${/^\d+$/.test(m.powerCycleNumber) ? 'Power cycle '+m.powerCycleNumber+' · ' : ''}Boot ${m.bootNumber} · Recording ${m.sessionNumber}` : 'Persistent boot order unavailable';
  const elapsed = s.end?.durationMs;
  const duration = elapsed && /^\d+$/.test(String(elapsed)) ? `${Math.floor(Number(elapsed)/60000)} min ${Math.floor(Number(elapsed)/1000)%60} sec` : '';
  const state = s.state === 'error' ? 'Error: ' + (m.detail || 'Device unavailable') : s.end ? `Finished (${s.end.outcome || 'unknown'})` : s.saving ? 'Saving · not finalized' : (m.saved === false || (s.state === 'listening' && s.saving === false)) ? 'Live captions · not saving' : 'No end record · live or interrupted';
  return [date, order, duration, state].filter(Boolean).join(' · ');
}
function renderLibrary() {
  const q = $('search').value.toLocaleLowerCase();
  const fragment = document.createDocumentFragment();
  for (const s of [...store.sessions.values()].sort(ordering)) {
    if (q && ![title(s), ...[...s.phrases.values()].map(p=>p.rawText)].join(' ').toLocaleLowerCase().includes(q)) continue;
    const b = document.createElement('button'); b.textContent = title(s); b.className = s.id === selected ? 'selected' : '';
    const detail = document.createElement('small'); detail.textContent = info(s); b.append(detail);
    b.onclick = () => { selected = s.id; following = false; textNodes.clear(); $('paragraphs').replaceChildren(); render(); renderAliases(); };
    fragment.append(b);
  }
  $('library').replaceChildren(fragment);
}
function renderAliases() {
  if ($('aliases').contains(document.activeElement)) return;
  $('aliases').replaceChildren();
  const s = store.sessions.get(selected); if (!s) return;
  const speakers = [...new Set([...s.labels.values()].filter(l=>l.ready && l.speaker>=0).map(l=>l.speaker))].sort();
  for (const speaker of speakers) {
    const row = document.createElement('div'), name = document.createElement('input');
    name.placeholder = `Person ${speaker+1}`; name.setAttribute('aria-label', name.placeholder); name.maxLength = 60;
    name.value = annotation(s.id).aliases[speaker] || '';
    name.onchange = () => { annotation(s.id).aliases[speaker] = name.value.trim(); render(); };
    row.append(name); $('aliases').append(row);
  }
}
function render() {
  renderLibrary();
  const s = store.sessions.get(selected); if (!s) return;
  $('title').textContent = title(s); $('metadata').textContent = info(s);
  if (document.activeElement !== $('rename')) $('rename').value = annotation(s.id).title;
  const viewport = $('transcript'); const oldScroll = viewport.scrollTop;
  // Keep the first visible source row anchored when late labels alter wrapping.
  const top = viewport.getBoundingClientRect().top;
  const anchor = [...textNodes].find(([,node]) => node.getBoundingClientRect().bottom > top);
  const anchorDelta = anchor ? anchor[1].getBoundingClientRect().top - top : 0;
  const rows = turns(s), keep = new Set(rows.map(r=>r.key));
  for (const [key, node] of textNodes) if (!keep.has(key)) { node.remove(); textNodes.delete(key); }
  let previous = null;
  for (const row of rows) {
    let node = textNodes.get(row.key);
    if (!node) { node = document.createElement('p'); textNodes.set(row.key, node); }
    const name = row.speaker === null ? (row.labelled ? '?: ' : '') : (annotation(s.id).aliases[row.speaker] || `Person ${row.speaker+1}`) + ': ';
    const value = name + row.text;
    if (node.textContent !== value) node.textContent = value;
    const expected = previous ? previous.nextSibling : $('paragraphs').firstChild;
    if (expected !== node) $('paragraphs').insertBefore(node, expected);
    previous = node;
  }
  const draft = s.draft?.text ? '~ ' + s.draft.text : '';
  if ($('draft').textContent !== draft) $('draft').textContent = draft;
  if (following) viewport.scrollTop = viewport.scrollHeight;
  else if (anchor && textNodes.has(anchor[0])) viewport.scrollTop += anchor[1].getBoundingClientRect().top - top - anchorDelta;
  else viewport.scrollTop = oldScroll;
  $('follow').textContent = following ? 'Following live' : 'Follow live';
}
function accept(event, live = false) {
  if (event.type === 'annotation') {
    if (typeof event.sessionId !== 'string') throw Error('Invalid annotations');
    const aliases = {};
    for (const [key,value] of Object.entries(event.aliases || {})) if (/^(?:[0-9]|1[0-5])$/.test(key) && typeof value === 'string') aliases[key] = value.slice(0,60);
    annotations.set(event.sessionId, {title:typeof event.title === 'string' ? event.title.slice(0,160) : '', aliases}); return;
  }
  if (event.type === 'message') { notify(event.text); return; }
  if (event.type === 'files') {
    $('files').replaceChildren();
    for (const name of event.files || []) {
      const b = document.createElement('button'); b.textContent = name;
      b.onclick = () => { selected = ''; textNodes.clear(); $('paragraphs').replaceChildren(); command('note read ' + name); }; $('files').append(b);
    }
    notify(event.truncated ? 'P4 list limited to 128 files; import SD files for the rest.' : `${(event.files || []).length} recording file(s) on P4.`);
    return;
  }
  if (event.type === 'archivePage') {
    if (!event.eof && typeof event.file === 'string' && Number.isSafeInteger(event.nextOffset) && event.nextOffset > 0) command('note read ' + event.file + ' ' + event.nextOffset);
    else notify('Recording loaded from P4.');
    return;
  }
  if (event.type === 'vocabulary') {
    notify(`Vocabulary refreshed: ${(event.words || []).length} term(s).`);
    $('vocabulary').replaceChildren();
    for (const word of event.words || []) {
      const row = document.createElement('div'), label = document.createElement('span'), remove = document.createElement('button');
      label.textContent = `${word.display} ← ${word.spoken}`; remove.textContent = 'Remove';
      remove.onclick = () => command('vocab remove ' + word.spoken); row.append(label,remove); $('vocabulary').append(row);
    }
    return;
  }
  const s = store.apply(event);
  if (event.type === 'status' && event.state === 'error') notify(event.detail || 'Device error');
  else if (event.type === 'status' && $('message').textContent.startsWith('Command sent;')) notify(`P4 ${event.state}${event.saving ? ' · saving' : ''}.`);
  if (s && (!selected || (live && following && event.type === 'start'))) { selected = s.id; textNodes.clear(); $('paragraphs').replaceChildren(); }
}
async function importText(text) {
  const {events:parsed, discardedTail} = parseRecording(text);
  // Validate complete records before adding them to the active viewer.
  const probe = new TranscriptStore();
  for (const e of parsed) if (e.type !== 'annotation') probe.apply(e);
  for (const e of parsed) accept(e);
  render(); renderAliases();
  return discardedTail;
}
$('import').onchange = async () => {
  try { let recovered = false; for (const file of $('import').files) { if (file.size > 16*1024*1024) throw Error('Import limited to 16 MiB per file'); recovered = await importText(await file.text()) || recovered; } notify(recovered ? 'Recovered complete records; an incomplete final write was discarded. Recording is unfinalized.' : 'Imported. Missing end records are shown as unfinalized.'); }
  catch(error) { notify(error.message); }
};
$('replay').onclick = async () => { try { await importText(await (await fetch('/replay.jsonl')).text()); notify('Demo replay loaded. Drafts and labels in this fixture are simulated; standalone hardware supplies finals.'); } catch(error) { notify(error.message); } };
$('search').oninput = renderLibrary;
$('set-title').onclick = () => { const s = store.sessions.get(selected); if (s) { annotation(s.id).title = $('rename').value.trim().slice(0,160); render(); } };
$('set-clock').onclick = () => command('clock set ' + Math.floor(Date.now()/1000));
$('add-word').onclick = () => command('vocab add ' + $('term').value.trim());
for (const b of document.querySelectorAll('[data-command]')) b.onclick = () => command(b.dataset.command);
$('follow').onclick = () => { following = true; render(); };
$('transcript').addEventListener('scroll', () => { const v = $('transcript'); following = v.scrollHeight - v.scrollTop - v.clientHeight < 40; });
$('download').onclick = () => {
  const s = store.sessions.get(selected); if (!s) return;
  const events = [{...s.metadata,schema:1,type:'start',sessionId:s.id}, ...[...s.phrases.values()].sort((a,b)=>a.sequence-b.sequence)];
  for (const [sequence,label] of s.labels) events.push({schema:1,type:'speaker',sessionId:s.id,sequence,...label});
  if (s.end) events.push(s.end);
  events.push({schema:1,type:'annotation',sessionId:s.id,...annotation(s.id)});
  const url = URL.createObjectURL(new Blob([events.map(e=>JSON.stringify(e)).join('\n')+'\n'], {type:'application/x-ndjson'}));
  const link = document.createElement('a'); link.href = url; link.download = s.id.replace(/[^a-zA-Z0-9_-]/g,'_') + '.jsonl'; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
};
async function poll() {
  if (busy) return; busy = true;
  try {
    const response = await fetch('/api/events?after='+cursor), data = await response.json();
    if (!response.ok) throw Error(data.error || 'Viewer unavailable');
    const changedConnection = connected !== data.usb; connected = data.usb;
    for (const b of document.querySelectorAll('[data-command], #set-clock, #add-word')) b.disabled = !connected;
    $('connection').textContent = connected ? 'USB connected · on-device recognition · local viewer' : 'Import and replay mode · no P4 USB connection';
    for (const item of data.events) accept(item.event, true);
    cursor = data.cursor;
    if (data.gap) notify('USB viewer history gap. Import the SD recording for the full transcript.');
    if (data.events.length) { render(); renderAliases(); }
    if (changedConnection && connected) { await command('status'); await command('vocab list'); }
  } catch(error) { notify(error.message); }
  finally { busy = false; setTimeout(poll,800); }
}
poll();
