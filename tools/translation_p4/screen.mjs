#!/usr/bin/env node
// Host quality/reference probe. This is not an ESP32-P4 runtime or RAM-fit test.
import {readFileSync, writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {runInThisContext} from 'node:vm';
import {isMainThread, Worker} from 'node:worker_threads';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import os from 'node:os';

const here = dirname(fileURLToPath(import.meta.url));
let networkAttempts = 0;
function rejectNetwork() {
  networkAttempts += 1;
  throw new Error('Offline screening forbids network access');
}
globalThis.fetch = rejectNetwork;
http.request = http.get = https.request = https.get = rejectNetwork;
net.connect = net.createConnection = net.Socket.prototype.connect = rejectNetwork;

const runtimeDir = resolve(here, 'private/runtime/package/worker');
const candidates = {
  mozilla: {
    directory: 'mozilla-enes', name: 'Mozilla tiny English-to-Spanish',
    files: {
      model: ['model.enes.intgemm.alphas.bin', 'fa7460037a3163e03fe1d23602f964bff2331da6ee813637e092ddf37156ef53'],
      shortlist: ['lex.50.50.enes.s2t.bin', '3a113d713dec3cf1d12bba5b138ae616e28bba4bbc7fe7fd39ba145e26b86d7f'],
      vocab: ['vocab.esen.spm', '909b1eea1face0d7f90a474fe29a8c0fef8d104b6e41e65616f864c964ba8845'],
    },
  },
  euronano: {
    directory: 'euronano-enxx', name: 'TranslatePsy-EuroNano Tiny en-xx',
    revision: '3a5e1e4e2f7001ff5cfd79785bef03cf19281b73',
    prefix: '##ES ',
    files: {
      model: ['model.intgemm.alphas.bin', '646c87844fd9917e929feed627ec7f21b245f7bfded5442b61dc8b4b1b1e68dd'],
      shortlist: ['lex.50.50.enxx.s2t.bin', '9e0c8b830ef2ac6eecc56c54c974d81b7610aa1d5b32063a1c27e8d27b6c630c'],
      vocab: ['vocab.spm', 'f76ce75a335872f27c812c7d122051f923565b5111adc36f207a15be4cbc9a51'],
    },
  },
};
const runtimeFiles = {
  'translator-worker.js': '90257af9ee0758983501bdce77ca7ec168cd7360d4689298c20a81b0251d6b62',
  'bergamot-translator-worker.js': '748b2418418a2ffc6e70721aeb10098d8e6fb589ea156b91f4ae8bc3490d8f7a',
  'bergamot-translator-worker.wasm': '95a2b58dd6773bf1b3f345d71f9149928b9f75f4ec9c9064c0b3e42c298671b2',
};

function checkedRead(path, expected) {
  const data = readFileSync(path);
  if (createHash('sha256').update(data).digest('hex') !== expected)
    throw new Error(`Pinned SHA256 mismatch: ${path}`);
  return data;
}

if (!isMainThread) {
  // The official 0.4.9 worker expects CommonJS globals even though its package
  // is ESM. Supply that environment without editing the verified source files.
  const filename = resolve(runtimeDir, 'translator-worker.js');
  globalThis.require = createRequire(filename);
  globalThis.__filename = filename;
  globalThis.__dirname = runtimeDir;
  for (const [name, hash] of Object.entries(runtimeFiles))
    checkedRead(resolve(runtimeDir, name), hash);
  runInThisContext(readFileSync(filename, 'utf8'), {filename});
  globalThis.screenNetworkAttempts = () => networkAttempts;
  runInThisContext(`worker.screenMemory = function() {
    return {
      wasm_linear_memory_bytes: this.module?.HEAP8?.buffer.byteLength ?? null,
      worker_js_memory: process.memoryUsage(),
      blocked_network_attempts: globalThis.screenNetworkAttempts()
    };
  };`);
} else {
  await main().catch(error => {
    console.error(error.stack || String(error));
    process.exitCode = 1;
  });
}

async function main() {
  const start = performance.now();
  const args = process.argv.slice(2);
  let fixturesPath = resolve(here, 'fixtures.json');
  let candidateKey = 'mozilla';
  let useShortlist = false;
  let text, outputPath;
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === '--help') {
      console.log('Usage: node screen.mjs [--candidate mozilla|euronano] [--shortlist | --no-shortlist] [--fixtures FILE | --text TEXT] [--output FILE]\nDefault: Mozilla English-to-Spanish, full output vocabulary (no shortlist).');
      return;
    }
    if (args[i] === '--no-shortlist' || args[i] === '--shortlist') {
      useShortlist = args[i] === '--shortlist';
      continue;
    }
    const flag = args[i];
    if (!['--candidate', '--fixtures', '--text', '--out', '--output'].includes(flag) || i + 1 >= args.length)
      throw new Error(`Unknown option or missing value: ${flag}`);
    const value = args[++i];
    if (flag === '--fixtures') fixturesPath = resolve(value);
    if (flag === '--text') text = value;
    if (flag === '--candidate') candidateKey = value;
    if (flag === '--out' || flag === '--output') outputPath = resolve(value);
  }
  const candidate = Object.hasOwn(candidates, candidateKey) ? candidates[candidateKey] : null;
  if (!candidate) throw new Error('Candidate must be mozilla or euronano');
  const modelDir = resolve(here, 'private', candidate.directory);
  const fixtures = text === undefined
    ? JSON.parse(readFileSync(fixturesPath, 'utf8'))
    : [{id: 'cli', category: 'manual', text, review_focus: 'Manual review required'}];
  if (!Array.isArray(fixtures) || !fixtures.length || fixtures.some(x =>
    typeof x.id !== 'string' || typeof x.text !== 'string' || !x.text.trim() || x.text.length > 1024))
    throw new Error('Expected nonempty fixture array with string IDs and 1–1024 character input text');

  const modelBuffers = {};
  const modelAssets = [];
  for (const [part, [name, hash]] of Object.entries(candidate.files)) {
    if (part === 'shortlist' && !useShortlist) continue;
    const data = checkedRead(resolve(modelDir, name), hash);
    modelBuffers[part] = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    modelAssets.push({part, filename: name, bytes: data.length, sha256: hash});
  }
  modelBuffers.vocabs = [modelBuffers.vocab];
  delete modelBuffers.vocab;
  if (!useShortlist) modelBuffers.shortlist = new ArrayBuffer(0);

  const thread = new Worker(new URL(import.meta.url), {stdout: true, stderr: true});
  // Keep stdout machine-readable if the upstream runtime emits diagnostics.
  thread.stdout.pipe(process.stderr);
  thread.stderr.pipe(process.stderr);
  let serial = 0;
  const pending = new Map();
  thread.on('message', ({id, result, error}) => {
    const job = pending.get(id);
    if (!job) return;
    clearTimeout(job.timer);
    pending.delete(id);
    if (error) job.reject(new Error(error.message || JSON.stringify(error)));
    else job.resolve(result);
  });
  const failPending = error => {
    for (const job of pending.values()) {
      clearTimeout(job.timer);
      job.reject(error);
    }
    pending.clear();
  };
  thread.on('error', failPending);
  thread.on('exit', code => failPending(new Error(`Translation worker exited: ${code}`)));
  function call(name, ...args) {
    return new Promise((resolve, reject) => {
      const id = ++serial;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`Translation worker timed out after 60s: ${name}`));
      }, 60_000);
      pending.set(id, {resolve, reject, timer});
      thread.postMessage({id, name, args});
    });
  }
  function modelInputs(source) {
    if (!candidate.prefix) return [source];
    // A multilingual model needs its language tag on every source sentence.
    return [...new Intl.Segmenter('en', {granularity: 'sentence'}).segment(source)]
      .map(({segment}) => candidate.prefix + segment.trim());
  }
  async function translate(source) {
    const inputs = modelInputs(source);
    const responses = await call('translate', {
      models: [{from: 'en', to: 'es'}],
      texts: inputs.map(text => ({text, html: false, qualityScores: false})),
    });
    return {text: responses.map(x => x.target.text).join(' '), inputs};
  }

  const baseline = process.memoryUsage();
  let sampledPeakRss = baseline.rss;
  const rssSampler = setInterval(() => {
    sampledPeakRss = Math.max(sampledPeakRss, process.memoryUsage().rss);
  }, 5);
  try {
    const initStart = performance.now();
    await call('initialize', {cacheSize: 0, useNativeIntGemm: false});
    const runtimeInitMs = performance.now() - initStart;
    const afterRuntime = await call('screenMemory');
    const modelStart = performance.now();
    await call('loadTranslationModel', {from: 'en', to: 'es'}, modelBuffers);
    const modelLoadMs = performance.now() - modelStart;
    const afterModel = await call('screenMemory');
    const setupMs = performance.now() - start;
    const rows = [];
    let coldTotalMs;
    for (const [i, fixture] of fixtures.entries()) {
      const tick = performance.now();
      const response = await translate(fixture.text);
      const elapsed = performance.now() - tick;
      if (i === 0) coldTotalMs = performance.now() - start;
      rows.push({...fixture, model_input_text: response.inputs.join('\n'),
        model_input_segments: response.inputs, translated_text: response.text,
        first_pass_ms: elapsed, first_pass_kind: i === 0 ? 'first_decode' : 'warm_decode'});
    }
    for (const row of rows) {
      const tick = performance.now();
      const response = await translate(row.text);
      row.warm_repeat_ms = performance.now() - tick;
      row.repeat_match = response.text === row.translated_text;
      if (!row.repeat_match) row.repeat_translated_text = response.text;
    }
    const finalWorker = await call('screenMemory');
    sampledPeakRss = Math.max(sampledPeakRss, process.memoryUsage().rss);
    const attempts = networkAttempts + finalWorker.blocked_network_attempts;
    if (attempts) throw new Error(`Offline run attempted network access ${attempts} times`);
    const report = {
      schema_version: 1,
      recorded_at: new Date().toISOString(),
      scope: 'Mac host text-to-text reference inference; not a P4 capability or RAM-fit result',
      host: {platform: process.platform, arch: process.arch, node: process.version,
        cpu: os.cpus()[0]?.model},
      runtime: {name: '@browsermt/bergamot-translator', version: '0.4.9',
        source_files_unmodified: true, engine: 'Bergamot WASM with embedded intgemm fallback',
        configured_workspace_mib: 128, workspace_override_supported: false,
        beam_size: 1, cache_size: 0, workers: 1,
        use_shortlist: useShortlist,
        shortlist_enabled: useShortlist,
        shortlist_configuration: useShortlist
          ? 'Verified shortlist buffer supplied to unchanged upstream loadTranslationModel'
          : 'Runner supplies an empty ArrayBuffer as shortlist; unchanged upstream code creates zero-length AlignedMemory and uses full output vocabulary',
        max_length_break: 128, max_length_factor: 2, mini_batch_words: 1024,
        note: 'Stock worker forcibly sets workspace=128; this probe does not reduce that setting'},
      direction: {from: 'en', to: 'es'},
      candidate: {id: candidateKey, name: candidate.name, revision: candidate.revision,
        input_prefix: candidate.prefix || '',
        sentence_segmentation: candidate.prefix ? 'Intl.Segmenter en sentence; prefix each segment' : 'Upstream Bergamot defaults'},
      offline: {local_assets_only: true, network_api_guards: ['fetch', 'http', 'https', 'net'],
        blocked_network_attempts: attempts,
        note: 'No model registry or remote translation service is contacted; setup downloads are separate'},
      model_assets: modelAssets,
      model_assets_total_bytes: modelAssets.reduce((sum, file) => sum + file.bytes, 0),
      timing_ms: {setup: setupMs, runtime_initialize: runtimeInitMs, model_load: modelLoadMs,
        first_decode: rows[0].first_pass_ms, cold_start_through_first_translation: coldTotalMs,
        warm_repeat_min: Math.min(...rows.map(x => x.warm_repeat_ms)),
        warm_repeat_max: Math.max(...rows.map(x => x.warm_repeat_ms))},
      memory: {process_baseline_after_asset_read: baseline,
        process_sampled_peak_rss_bytes: sampledPeakRss,
        process_lifetime_max_rss_bytes: process.resourceUsage().maxRSS * 1024,
        after_runtime: afterRuntime, after_model: afterModel, after_inference: finalWorker,
        note: 'RSS includes Node, JS buffers, worker and WASM. WASM linear memory is heap capacity, not live allocations. Neither predicts native P4 minimum RAM.'},
      results: rows,
    };
    const json = JSON.stringify(report, null, 2) + '\n';
    if (outputPath) writeFileSync(outputPath, json, {flag: 'wx'});
    process.stdout.write(json);
  } finally {
    clearInterval(rssSampler);
    await thread.terminate();
    failPending(new Error('Worker stopped'));
  }
}
