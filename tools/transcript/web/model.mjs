// One event contract for real standalone drafts/finals/optional speaker labels
// and explicitly simulated replay fixtures. It never changes speaker decisions.
export class TranscriptStore {
  constructor() { this.sessions = new Map(); }
  apply(input) {
    if (!input || typeof input !== 'object' || input.schema !== 1) throw Error('Unsupported event schema');
    const e = input.type === 'archive' ? input.record : input;
    if (!e || e.schema !== 1) throw Error('Invalid archived record');
    if (!['start', 'final', 'draft', 'speaker', 'end', 'status'].includes(e.type)) return null;
    if (typeof e.sessionId !== 'string' || !e.sessionId || e.sessionId.length > 120) throw Error('Missing session ID');
    let s = this.sessions.get(e.sessionId);
    if (!s) {
      if (this.sessions.size >= 128) throw Error('Viewer holds 128 recordings; reload before importing more');
      s = {id:e.sessionId, metadata:{}, phrases:new Map(), labels:new Map(), draft:null, lastFinal:0, end:null, state:'unknown', title:''};
      this.sessions.set(s.id, s);
    }
    if (e.type === 'start') { s.metadata = {...s.metadata, ...e}; s.saving = e.saved === true; }
    if (e.type === 'status') { s.state = e.state; s.saving = e.saving; s.metadata = {...s.metadata, ...e}; if (e.title && !s.title) s.title = String(e.title).slice(0,160); }
    if (e.type === 'final') {
      if (!Number.isSafeInteger(e.sequence) || e.sequence < 1 || typeof e.rawText !== 'string' || typeof e.text !== 'string' || e.text.length > 8192 || e.rawText.length > 8192) throw Error('Invalid final phrase');
      if (!s.phrases.has(e.sequence) && s.phrases.size >= 20000) throw Error('Recording exceeds viewer phrase limit');
      const old = s.phrases.get(e.sequence);
      if (old && (old.rawText !== e.rawText || old.text !== e.text)) throw Error('Conflicting repeated final phrase');
      s.phrases.set(e.sequence, {...e});
      s.lastFinal = Math.max(s.lastFinal, e.sequence);
      if (s.draft && s.draft.sequence <= e.sequence) s.draft = null;
      if (e.title && !s.title) s.title = String(e.title).slice(0, 160);
    }
    if (e.type === 'draft') {
      if (!Number.isSafeInteger(e.sequence) || e.sequence < 1 || !Number.isSafeInteger(e.version) || e.version < 0 || typeof e.text !== 'string' || e.text.length > 8192) throw Error('Invalid draft');
      if (e.sequence > s.lastFinal && (!s.draft || e.sequence > s.draft.sequence || (e.sequence === s.draft.sequence && e.version > s.draft.version))) s.draft = {...e};
    }
    if (e.type === 'speaker') {
      if (!Number.isSafeInteger(e.sequence) || e.sequence < 1 || !Number.isInteger(e.speaker) || e.speaker < -1 || e.speaker > 15 || typeof e.ready !== 'boolean') throw Error('Invalid speaker update');
      if (s.labels.size >= 20000 && !s.labels.has(e.sequence)) throw Error('Speaker history exceeds viewer limit');
      s.labels.set(e.sequence, {speaker:e.speaker, ready:e.ready});
    }
    if (e.type === 'end') { s.end = e; s.draft = null; s.state = 'done'; s.saving = false; }
    return s;
  }
}
export function turns(session) {
  const rows = []; let previous = null;
  const labelled = session.labels.size > 0;
  for (const p of [...session.phrases.values()].sort((a,b) => a.sequence - b.sequence)) {
    const label = session.labels.get(p.sequence);
    const speaker = label?.ready && label.speaker >= 0 ? label.speaker : null;
    const contiguous = previous !== null && p.sequence === previous + 1;
    const tail = rows.at(-1);
    if (tail && contiguous && ((!labelled) || (speaker !== null && speaker === tail.speaker))) {
      tail.text += ' ' + p.text; tail.raw += ' ' + p.rawText;
    } else rows.push({key:p.sequence, speaker, text:p.text, raw:p.rawText, labelled});
    previous = p.sequence;
  }
  return rows;
}
export function ordering(a,b) {
  // Group independent ordering domains; counters from different devices or
  // NVS generations have no chronological relationship.
  const x = a.metadata, y = b.metadata;
  const domain = String(x.orderingDomain || "unscoped").localeCompare(String(y.orderingDomain || "unscoped"));
  if (domain) return domain;
  if (!!x.bootDurable !== !!y.bootDurable) return x.bootDurable ? -1 : 1;
  if (x.orderingDomain === y.orderingDomain && x.bootDurable && y.bootDurable && /^\d+$/.test(x.bootNumber) && /^\d+$/.test(y.bootNumber)) {
    const boot = BigInt(y.bootNumber) - BigInt(x.bootNumber);
    if (boot) return boot > 0n ? 1 : -1;
    const session = BigInt(/^\d+$/.test(y.sessionNumber) ? y.sessionNumber : '0') - BigInt(/^\d+$/.test(x.sessionNumber) ? x.sessionNumber : '0');
    if (session) return session > 0n ? 1 : -1;
  }
  if (!!x.clockKnown !== !!y.clockKnown) return x.clockKnown ? -1 : 1;
  if (x.clockKnown && y.clockKnown) return String(y.startedUtc).localeCompare(String(x.startedUtc));
  return b.id.localeCompare(a.id);
}

// Recover complete records preceding a torn final write. Only an unterminated
// final line may be discarded; corruption in the middle is never hidden.
export function parseRecording(text) {
  const lines = text.split(/\r?\n/), events = [];
  if (lines.length > 60001) throw Error('Import has too many records');
  let discardedTail = false;
  for (let i = 0; i < lines.length; ++i) {
    const line = lines[i]; if (!line.trim()) continue;
    try { events.push(JSON.parse(line.startsWith('STT_EVENT ') ? line.slice(10) : line)); }
    catch (error) {
      if (i === lines.length - 1 && !text.endsWith('\n') && events.length) discardedTail = true;
      else throw Error(`Invalid recording JSON at line ${i+1}`);
    }
  }
  return {events, discardedTail};
}
