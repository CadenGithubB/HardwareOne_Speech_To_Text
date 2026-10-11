#!/usr/bin/env python3
"""Static (no-JavaScript) HTML summary of the STT speed and accuracy work, with inline SVG charts."""
import os
import html
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / 'docs' / 'Version Report.html'
extra = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else {}
BD = json.loads(Path(__file__).with_name('breakdown.json').read_text())
LAYERS = json.loads(Path(__file__).with_name('layers.json').read_text())
V = json.loads(Path(__file__).with_name('versions.json').read_text())   # versions.py: per-version session numbers
SESS = Path(os.environ.get('HW1_STT_SESSIONS', Path(__file__).resolve().parents[1] / 'device_tests' / 'speaker' / 'sessions'))
CMP_LONG = json.loads((SESS / 'compare_b18L-c9n_vs_b18L-c11n.json').read_text())['metrics']['L_speech']['all']
CMP_SPK = json.loads((SESS / 'compare_b25C-c11n-nospk_vs_b25C-c13n-async.json').read_text())['metrics']

BLUE, GREEN, RED, GREY, AMBER = '#2563eb', '#16a34a', '#dc2626', '#9ca3af', '#d97706'


def hbars(rows, unit, width=760, label_w=300, bar_h=26, gap=10, vmax=None, fmt='{:.2f}', note_w=150):
    """rows: (label, value, colour, note). Horizontal bars, value labels at the bar end."""
    vmax = vmax or max(r[1] for r in rows) * 1.08
    plot_w = width - label_w - note_w
    h = len(rows) * (bar_h + gap) + gap
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">']
    for i, (label, value, colour, note) in enumerate(rows):
        y = gap + i * (bar_h + gap)
        w = max(2, plot_w * value / vmax)
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h * 0.68}" text-anchor="end" class="lbl">{html.escape(label)}</text>')
        out.append(f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="4" fill="{colour}"/>')
        out.append(f'<text x="{label_w + w + 6:.1f}" y="{y + bar_h * 0.68}" class="val">{fmt.format(value)} {unit}</text>')
        if note:
            out.append(f'<text x="{width - 4}" y="{y + bar_h * 0.68}" text-anchor="end" class="note">{html.escape(note)}</text>')
    out.append('</svg>')
    return '\n'.join(out)


def deltas(rows, width=900, label_w=320, bar_h=24, gap=9, span=650):
    """rows: (label, delta_ms, note). Left of zero = faster (green), right = slower (red).
    Bars longer than span are clipped and their value is written inside the bar."""
    left = 300                      # px available left of the zero line
    zero = label_w + left
    scale = (left - 10) / span
    h = len(rows) * (bar_h + gap) + gap + 18
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">',
           f'<line x1="{zero}" y1="0" x2="{zero}" y2="{h - 16}" stroke="#6b7280" stroke-width="1"/>',
           f'<text x="{zero - 6}" y="{h - 3}" text-anchor="end" class="note">← faster</text>',
           f'<text x="{zero + 6}" y="{h - 3}" class="note">slower →</text>']
    for i, (label, d, note) in enumerate(rows):
        y = gap + i * (bar_h + gap)
        clipped = abs(d) > span
        w = min(abs(d), span) * scale
        x = zero - w if d < 0 else zero
        colour = (GREY if 'rejected' in note.lower() else GREEN) if d < 0 else RED
        txt = (f'{d/1000:+.1f} s' if clipped else f'{d:+.0f} ms') + (f'  ({note})' if note else '')
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h * 0.7}" text-anchor="end" class="lbl">{html.escape(label)}</text>')
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{max(w, 2):.1f}" height="{bar_h}" rx="3" fill="{colour}"/>')
        if clipped:
            out.append(f'<text x="{x + 8:.1f}" y="{y + bar_h * 0.7}" class="val" style="fill:#fff">{html.escape(txt)}</text>')
        elif d < 0:
            # value on the right of the zero line keeps it clear of long labels
            out.append(f'<text x="{zero + 8:.1f}" y="{y + bar_h * 0.7}" class="val">{html.escape(txt)}</text>')
        else:
            out.append(f'<text x="{x + w + 6:.1f}" y="{y + bar_h * 0.7}" class="val">{html.escape(txt)}</text>')
    out.append('</svg>')
    return '\n'.join(out)


def stacked(rows, segs, width=760, label_w=230, bar_h=34, gap=16, vmax=3.8, unit='s', digits=2, legend=True):
    """rows: (label, [values per segment]); segs: (name, colour). The legend wraps and is sized to fit."""
    plot_w = width - label_w - 70
    spots, lx, ly = [], label_w, 0
    for name, colour in segs:
        step = 16 + 7.2 * len(name) + 22
        if lx + step > width:
            lx, ly = label_w, ly + 18
        spots.append((lx, ly, name, colour))
        lx += step
    bars_h = len(rows) * (bar_h + gap) + gap
    h = bars_h + (ly + 18 + 16 if legend else 4)
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">']
    for i, (label, vals) in enumerate(rows):
        y = gap + i * (bar_h + gap)
        x = label_w
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h * 0.62}" text-anchor="end" class="lbl">{html.escape(label)}</text>')
        for (name, colour), v in zip(segs, vals):
            w = plot_w * max(v, 0) / vmax
            if w > 0.5:
                out.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{colour}"><title>{html.escape(name)}: {v:.{digits}f} {unit}</title></rect>')
            x += w
        out.append(f'<text x="{x + 6:.1f}" y="{y + bar_h * 0.62}" class="val">{sum(vals):.{digits}f} {unit}</text>')
    if legend:
        for lx, ly, name, colour in spots:
            y0 = bars_h + 8 + ly
            out.append(f'<rect x="{lx}" y="{y0}" width="12" height="12" fill="{colour}"/>')
            out.append(f'<text x="{lx + 16}" y="{y0 + 10}" class="note">{html.escape(name)}</text>')
    out.append('</svg>')
    return '\n'.join(out)



def pipeline(rows, width=900, box_w=150, box_h=58, hgap=28, vgap=46):
    """rows: list of rows of (title, subtitle, colour). Boxes left to right with arrows; rows joined by a down arrow."""
    h = len(rows) * (box_h + vgap)
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">',
           '<defs><marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#6b7280"/></marker></defs>']
    for r, row in enumerate(rows):
        y = 8 + r * (box_h + vgap)
        for i, (title, sub, colour) in enumerate(row):
            x = 8 + i * (box_w + hgap)
            out.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8" fill="none" stroke="{colour}" stroke-width="2.5"/>')
            out.append(f'<text x="{x + box_w/2}" y="{y + 24}" text-anchor="middle" class="val">{html.escape(title)}</text>')
            out.append(f'<text x="{x + box_w/2}" y="{y + 43}" text-anchor="middle" class="note">{html.escape(sub)}</text>')
            if i + 1 < len(row):
                out.append(f'<line x1="{x + box_w + 2}" y1="{y + box_h/2}" x2="{x + box_w + hgap - 3}" y2="{y + box_h/2}" stroke="#6b7280" stroke-width="2" marker-end="url(#ar)"/>')
        if r + 1 < len(rows):
            xl = 8 + (len(row) - 1) * (box_w + hgap) + box_w / 2
            out.append(f'<path d="M{xl},{y + box_h + 2} L{xl},{y + box_h + vgap/2} L{8 + box_w/2},{y + box_h + vgap/2} L{8 + box_w/2},{y + box_h + vgap - 4}" fill="none" stroke="#6b7280" stroke-width="2" marker-end="url(#ar)"/>')
    out.append('</svg>')
    return '\n'.join(out)

# --- data (all measured in this project; see the notes under each chart) ---------------------------------
train_time = hbars([
    ('Before (500 h run)', 33.1, GREY, 'measured, Oct 7-8'),
    ('With trainer speedups', 9.7, GREEN, 'components measured'),
], 'h', vmax=36, fmt='{:.1f}')
train_parts = stacked([
    ('Before', [26.6, 5.8, 0.6]),
    ('After (projected)', [8.6, 0.45, 0.63]),
], [('training steps', BLUE), ('checkpoint scoring', AMBER), ('test sets', GREY)], vmax=36, unit='h', digits=1)

broad = hbars([
    ('NVIDIA original', 26.83, GREY, ''),
    ('Old P4 model (general)', 23.11, GREY, ''),
    ('general2, LR 2e-5', 23.92, AMBER, ''),
    ('general + noise clips', 23.18, BLUE, ''),
    ('ON THE P4: general2, LR 1e-5', 22.80, GREEN, 'best'),
], '%', vmax=30, fmt='{:.2f}')
phantom = hbars([
    ('NVIDIA original', 18.8, GREY, ''),
    ('Old P4 model (general)', 30.1, RED, ''),
    ('general2, LR 2e-5', 8.0, GREEN, ''),
    ('general + noise clips', 8.8, GREEN, ''),
    ('ON THE P4: general2, LR 1e-5', 9.5, GREEN, '-68% vs old'),
], 'words/min', vmax=34, fmt='{:.1f}')

x_row = []
if extra.get('c3x_speech'):
    x_row = [('Design version + explicit PSRAM (final)', extra['c3x_speech'], GREEN, extra.get('c3x_note', ''))]
TODAY = BD['b9-c4an/all']['median_L']
def sess_note(v):
    n = V[v]['sessions']
    return f"{n} session{'s' if n != 1 else ''}, {V[v]['phrases']} phrases"
LATER = ('1.4', '1.5', '1.6', '1.7', '1.8')
caption = hbars([
    ('1.1', 3.61, GREY, 'all phrases'),
    ('1.1 + cache, -O2, model reuse', 2.90, BLUE, 'step toward 1.2'),
    ('1.2', 1.69, BLUE, ''),
    ('1.3', TODAY, BLUE, sess_note('1.3')),
] + [(v, V[v]['all'], GREEN, sess_note(v)) for v in LATER], 's', vmax=4.0, fmt='{:.2f}', note_w=210)
short = hbars([
    ('1.1', 3.4, GREY, 'and up to 17 s when merged'),
    ('1.1 + cache, -O2, model reuse', 3.6, BLUE, 'step toward 1.2'),
    ('1.2', 1.45, BLUE, '1-s close for short replies'),
    ('1.3', BD['b9-c4an/short']['median_L'], BLUE, 'head start in the pause'),
] + [(v, V[v]['short'], GREEN, '1 session' if V[v]['sessions'] == 1 else '') for v in LATER],
    's', vmax=4.0, fmt='{:.2f}', note_w=230)
longer = hbars([
    ('1.1', BD['e0n/longer']['median_L'], GREY, ''),
    ('1.2', BD['b6-c3xn/longer']['median_L'], BLUE, ''),
    ('1.3', BD['b9-c4an/longer']['median_L'], BLUE, 'faster model'),
] + [(v, V[v]['longer'], GREEN, '1 session' if V[v]['sessions'] == 1 else '') for v in LATER],
    's', vmax=4.0, fmt='{:.2f}', note_w=230)
ALLV = ('1.1', '1.2', '1.3') + LATER
model_speed = hbars([(v, V[v]['model_ms_per_audio_s'], GREY if v == '1.1' else (BLUE if v in ('1.2', '1.3') else GREEN), '')
                     for v in ALLV], 'ms per audio-s', vmax=460, fmt='{:.0f}', note_w=60)
lm_step = hbars([(v, V[v]['lm_ms'], GREY if v == '1.1' else (BLUE if v in ('1.2', '1.3') else GREEN),
                  'faster decoder' if v == '1.4' else '') for v in ALLV], 'ms', vmax=175, fmt='{:.0f}', note_w=120)
long_speech = hbars([
    ('1.6 (20 s phrase cap)', CMP_LONG['A_median'] / 1000, BLUE, ''),
    ('1.7 (10 s phrase cap)', CMP_LONG['B_median'] / 1000, GREEN, f"per clip: median {CMP_LONG['median_delta']:+.0f} ms, mean {CMP_LONG['mean_delta']:+.0f} ms"),
], 's', vmax=2.6, fmt='{:.2f}', note_w=330)
SEGS = [('wait', 'waiting for the phrase to end', GREY), ('trigger', 'head start: 200 ms of quiet', '#cbd5e1'),
        ('queue', 'waiting for the processor', '#a78bfa'), ('rebuild', 'model rebuild', AMBER),
        ('features', 'audio features', '#0891b2'), ('pw', 'model: pointwise layers', '#1d4ed8'),
        ('dw', 'model: depthwise layers', '#60a5fa'), ('other', 'model: adds and others', '#93c5fd'),
        ('lm', 'language model', GREEN), ('delivery', 'hand-off to the caption', '#db2777')]
def stage_chart(cat, vmax, legend):
    rows = [(name, [BD[f'{key}/{cat}'][k] for k, _, _ in SEGS]) for name, key in
            (('1.1', 'e0n'), ('1.2', 'b6-c3xn'), ('1.3', 'b9-c4an'), ('1.4', 'v1.4'), ('1.5', 'v1.5'),
             ('1.6', 'v1.6'), ('1.7', 'v1.7'), ('1.8', 'v1.8'))]
    return stacked(rows, [(n, c) for _, n, c in SEGS], vmax=vmax, label_w=150, width=860, legend=legend)
stages_all = stage_chart('all', 4.8, True)
stages_short = stage_chart('short', 4.8, False)
stages_long = stage_chart('longer', 4.8, False)
layer_rows = [(name, [LAYERS[key][t] for t in ('pw512', 'pw256', 'pwhead', 'dw75', 'dw63', 'dw51', 'dw87', 'dw39_33', 'addrelu')])
              for name, key in (('1.1*', 'old'), ('1.2', 'design'), ('1.3, 1.4', 'today'), ('1.5-1.8', 'c12'))]
layers = stacked(layer_rows, [('pointwise 512x512 (53)', '#1d4ed8'), ('pointwise 256x256 (36)', '#3b82f6'),
                              ('pointwise head + first (5)', '#93c5fd'), ('depthwise k75 (15)', '#0f766e'),
                              ('depthwise k63 (15)', '#14b8a6'), ('depthwise k51 (15)', '#5eead4'),
                              ('depthwise k87 dilated (1)', '#a7f3d0'), ('depthwise k33/k39 (31)', '#d1fae5'),
                              ('adds + ReLU (30)', AMBER)], vmax=2.6, label_w=150, width=860)

device_deltas = deltas([
    ('Larger cache line (128 B L2)', -344, ''),
    ('Build the model once per session', -187, 'now in PSRAM'),
    ('Faster memory clock 250 MHz', -68, 'not used yet'),
    ('Compiler -O2 for speech code', -41, ''),
    ('Features computed while you talk', -120, ''),
    ('Cheaper pause between model stages', -69, ''),
    ('16 KB filter tiles', -58, ''),
    ('Early final + silence trim', -501, ''),
    ('Short replies close after 1 s silence', -2200, 'short replies'),
    ('Both cores for long filters', +81, 'rejected'),
    ('Smaller frame tiles', +255, 'rejected'),
    ('Depthwise in 64-channel blocks', -320, '6.6 s input; 0 on 4 s'),
    ('+ both cores, split by channels', -107, '4 s input; -96 on 2.5 s'),
    ('+ 64-step pointwise tiles', -92, '4 s; -136 on 6.6 s'),
    ('Head start for short replies', -590, 'short replies, median'),
    ('Bigger 256 KB cache (4 s input)', -240, 'Rejected for excessive RAM consumption'),
    ('1.4: faster LM decoder', V['1.4']['lm_ms'] - V['1.3']['lm_ms'], 'LM step per phrase, same text'),
    ('1.5: layer setups prepared once', -50, '43-57 ms, fixed audio; 0 internal RAM'),
    ('Tail 100 ms instead of 200 ms (long phrases)', -147, 'rejected: +1.1 WER points'),
    ('Tail 150 ms instead of 200 ms', -22, 'rejected: no clear gain'),
    ('Pointwise split by channels', +286, 'rejected (4 s input)'),
    ('Vector ReLU (branch only)', -7, '3-10 ms, fixed audio'),
    ('1.6: grab audio from a running preview', -32, 'head-start wait, longer phrases'),
    ('16 ms mic chunks', +24, 'rejected: -22 ms short, +21-27 ms longer'),
    ('1.7: 10 s phrase cap', CMP_LONG['median_delta'], 'long speech; +3.8 MB PSRAM free'),
    ('2.0: speaker labels in background', CMP_SPK['L_speech']['all']['median_delta'], 'no caption cost (matched)'),
], width=1000)

def vcol(v):
    return GREY if v == '1.1' else (BLUE if v in ('1.2', '1.3') else GREEN)
SPK16 = V['speaker_sessions']['1.6M LM']
SPK25 = V['speaker_sessions']['2.5M LM']
psram_low = hbars([(v, V[v]['psram_low_mb'], vcol(v), 'model rebuilt per phrase' if v == '1.1' else ('LM 1.6 MB' if v == '1.8' else ''))
                   for v in ALLV] + [('2.0 (with 2.5 MB LM)', SPK25['psram_low_mb'], AMBER, 'speaker model 3.4 MB'),
                                     ('2.0 (with 1.6 MB LM)', SPK16['psram_low_mb'], GREEN, 'shipped combination')],
                  'MB', vmax=7.5, fmt='{:.2f}', note_w=200)
psram_long = hbars([('1.6, long speech', V['long']['1.6']['psram_low_mb'], BLUE, '20 s phrase buffers'),
                    ('1.7, long speech', V['long']['1.7']['psram_low_mb'], GREEN, '10 s phrase buffers')],
                   'MB', vmax=7.5, fmt='{:.2f}', note_w=200)
internal_low = hbars([(v, V[v]['internal_low_kb'], vcol(v), 'dip in each phrase rebuild' if v == '1.1' else
                       ('test setup: +17 KB at boot from batch 17' if v == '1.7' else '')) for v in ALLV] +
                     [('2.0', min(SPK25['internal_low_kb'], SPK16['internal_low_kb']), AMBER, 'speaker model load')],
                     'KB', vmax=180, fmt='{:.0f}', note_w=250)
accuracy = hbars([(v, V[v]['clip_wer'], vcol(v), f"{V[v]['sessions']} session{'s' if V[v]['sessions'] != 1 else ''}, {V[v]['clip_wer_clips']} of 27 clips")
                  for v in ALLV], '%', vmax=26, fmt='{:.1f}', note_w=190)
lm_sizes = hbars([
    ('No language model', 21.75, RED, ''),
    ('1.0 MB', 18.79, BLUE, ''),
    ('1.6 MB', 18.70, BLUE, ''),
    ('2.5 MB (1.1-1.7)', 18.70, GREY, ''),
    ('4.0 MB', 18.51, BLUE, ''),
    ('1.6 MB + 9.2k tech terms (1.8)', 18.56, GREEN, 'chosen'),
], '%', vmax=24, fmt='{:.2f}', note_w=90)
lm_tech = hbars([
    ('No language model', 52.64, RED, '11 of 126'),
    ('2.5 MB (1.1-1.7)', 50.14, GREY, '8 of 126'),
    ('1.6 MB + tech terms (1.8)', 49.91, GREEN, '16 of 126'),
    ('2.5 MB + terms + Wikipedia', 49.40, BLUE, '18 of 126'),
    ('4.0 MB + terms + Wikipedia', 49.44, BLUE, '18 of 126'),
], '%', vmax=58, fmt='{:.1f}', note_w=110)
spk_acc = hbars([
    ('Mac: audiobooks', 95.4, BLUE, '21 conversations'),
    ('Mac: parliament', 93.5, BLUE, '21 conversations'),
    ('Mac: meetings', 79.6, BLUE, 'short turns'),
    ('P4: 4 conversations (1.9)', 91.0, GREEN, '2-4 people each'),
], '%', vmax=105, fmt='{:.0f}', note_w=150)
spk_time = hbars([
    ('1.9, first build', 1.42, GREY, 'in the speech worker'),
    ('1.9, kernels + 3x3 blocking', 0.68, BLUE, 'in the speech worker'),
    ('2.0', 0.68, GREEN, 'background task, captions never wait'),
], 's per phrase', vmax=1.7, fmt='{:.2f}', note_w=250)

trainer_deltas = hbars([
    ('Stock trainer', 18.5, GREY, ''),
    ('Depthwise-conv fix + masks + fused AdamW', 55.1, GREEN, '3.0x'),
], 'audio-s/s', vmax=62, fmt='{:.1f}')
eval_time = hbars([
    ('Checkpoint scoring on the CPU', 1300, GREY, '16 per run'),
    ('On the graphics chip', 109, GREEN, 'same scores'),
], 's', vmax=1450, fmt='{:.0f}')


g2_pipe = pipeline([
    [('G2 mic', 'left temple', GREY), ('LC3 encode', '10 ms frames', GREY), ('Bluetooth LE', '1 packet / 50 ms', GREY), ('C6 radio chip', 'to the P4 (SDIO)', GREY), ('LC3 decode', 'on the P4', GREY)],
    [('Phrase detector', 'end + short replies', GREEN), ('Speech model', 'int8, ESP-DL', GREEN), ('Language model', 'word search', GREEN), ('Caption sender', 'wakes on publish', GREEN), ('Bluetooth LE', 'right temple', GREY)],
])
g2_time = stacked([
    ('1.1', [0.08, 0.60, BD['e0n/longer']['median_L'] - 0.60, 0.11, 0.07]),
    ('1.2', [0.08, 0.00, BD['b6-c3xn/longer']['median_L'], 0.00, 0.07]),
    ('1.3', [0.08, 0.00, BD['b9-c4an/longer']['median_L'], 0.00, 0.07]),
] + [(v, [0.08, 0.00, BD[f'v{v}/longer']['median_L'], 0.00, 0.07]) for v in LATER],
    [('mic audio over Bluetooth (est.)', '#64748b'), ('end-of-phrase wait', GREY), ('speech processing', BLUE),
    ('caption timer', AMBER), ('caption to glasses + ack', GREEN)], vmax=4.0)
g2_short = stacked([
    ('1.1', [0.08, 3.40, 0.11, 0.07]),
    ('1.2', [0.08, 1.45, 0.00, 0.07]),
    ('1.3', [0.08, BD['b9-c4an/short']['median_L'], 0.00, 0.07]),
] + [(v, [0.08, BD[f'v{v}/short']['median_L'], 0.00, 0.07]) for v in LATER],
    [('mic audio over Bluetooth (est.)', '#64748b'), ('wait + processing', BLUE), ('caption timer', AMBER), ('caption to glasses + ack', GREEN)], vmax=4.0)

timeline = [
    ('Oct 3', 'General model on the P4 (Broad 23.11). Data moved to one external SSD.'),
    ('Oct 5', 'Noise-only clip bug found and fixed (they were ~90% of the training signal). User: train from the ground up.'),
    ('Oct 6-7', 'LR test: 2e-5 hurt early and never fully recovered; 1e-5 matched then beat the old model.'),
    ('Oct 8', 'general2 1e-5: best model yet (Broad 22.80, invented words 30 -> 9.5 per minute).'),
    ('Oct 9', 'Deployed to the P4. Speed audit: 9 measurements, 54 ideas, 126 agents. Trainer 3x faster.'),
    ('Oct 10', 'Six rounds of on-chip tests through the speaker and the P4 mic: caption delay 3.6 s -> ~1.7 s.'),
    ('Oct 10 (eve)', 'Per-layer timing on the chip: depthwise layers were 9% of the math but 34% of the time. Reordered (bit-identical) and head start for short replies: ~1.7 s -> ~1.1 s. Bigger cache measured, rejected (RAM).'),
    ('Oct 10 (18:30)', '1.4: the language-model decoder rewritten, 63% faster on the P4 with identical text. All of 1.3 ported to the local stt-speedups branch.'),
    ('Oct 11 (00:00-03:30)', '1.5: every layer\'s setup prepared once per session (no internal RAM). Its first build pushed free PSRAM under the LM\'s 6 MB load rule, so the LM did not load; fixed. Tail tests: 100 ms cost 1.1 points of accuracy, 150 ms gained nothing clear; 200 ms kept.'),
    ('Oct 11 (03:00-05:10)', '1.6: the head start takes the audio straight away even while a preview runs (wait 77 -> 45 ms). 16 ms mic chunks measured and rejected: the model ran 3% slower.'),
    ('Oct 11 (05:30)', '1.7: continuous phrases capped at 10 s. On long unbroken speech the lowest free PSRAM went from 1.6 to 5.4 MB.'),
    ('Oct 11 (06:00-08:20)', 'LM probe: decode time is set by the speech, not by memory or load, and LM size changes memory, not speed. Tech vocabulary (9.2k terms) built; 1.8 = a 1.6 MB LM with the terms: same accuracy, 0.9 MB less PSRAM.'),
    ('Oct 11 (08:30-09:35)', '1.9: speaker labels on the P4 (91% of phrases right). 2.0: labelling moved to a background task; that exposed an ESP-IDF bug (a vector register not saved on task switches), fixed with the upstream patch.'),
    ('Oct 11 (10:15-11:00)', '1.6 MB LM installed on the card, speaker kernels trimmed, labelled transcript lines, diagnostics compiled out. Everything ported to the stt-speedups branch (builds, host tests pass).'),
]
VERSIONS = [
    ('1.1', 'Oct 10', 'deployed', 'The firmware on the P4 (gen2-25397). The model is rebuilt for every phrase.'),
    ('1.2', 'Oct 10, afternoon', 'c3x', 'Design version: early final, short-reply rule, model kept for the session with its bookkeeping in PSRAM.'),
    ('1.3', 'Oct 10, evening', 'c4a', 'Faster depthwise layers on both cores; head start for short replies.'),
    ('1.4', 'Oct 10, 18:30', 'c5', 'Faster language-model decoder (identical text).'),
    ('1.5', 'Oct 11, 00:45', 'c7', 'Each layer\'s setup prepared once per session; 200 ms tail confirmed.'),
    ('1.6', 'Oct 11, 03:15', 'c9', 'Head start grabs the audio at once, even while a preview runs.'),
    ('1.7', 'Oct 11, 05:30', 'c11', 'Continuous phrases capped at 10 s (half the session audio buffers).'),
    ('1.8', 'Oct 11, 08:20', 'c12 + card LM', '1.6 MB language model with 9.2k tech terms (43k words) instead of 2.5 MB.'),
    ('1.9', 'Oct 11, 08:30', 'c13, first', 'Speaker labels ("Person N"), computed in the speech worker.'),
    ('2.0', 'Oct 11, 09:20-10:45', 'c13, final', 'Speaker labels in a background task, ESP-IDF fix, trimmed kernels, labelled transcript lines.'),
]

css = """
:root { --bg:#ffffff; --fg:#111827; --muted:#6b7280; --card:#f9fafb; --line:#e5e7eb; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#0b0f17; --fg:#e5e7eb; --muted:#9ca3af; --card:#111827; --line:#1f2937; } }
:root[data-theme="dark"] { color-scheme: dark; --bg:#0b0f17; --fg:#e5e7eb; --muted:#9ca3af; --card:#111827; --line:#1f2937; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 28px 16px 48px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 34px 0 6px; padding-top: 14px; border-top: 1px solid var(--line); }
h3 { font-size: 15px; margin: 18px 0 4px; color: var(--muted); font-weight: 600; }
p, li { color: var(--fg); }
.sub { color: var(--muted); margin: 0 0 18px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0 6px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.card .big { font-size: 24px; font-weight: 700; }
.card .from { color: var(--muted); font-size: 13px; }
svg text { fill: var(--fg); font-size: 13px; }
svg text.note { fill: var(--muted); font-size: 12px; }
svg text.val { font-weight: 600; }
.foot { color: var(--muted); font-size: 13px; margin-top: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
td { padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
td:first-child { white-space: nowrap; color: var(--muted); width: 80px; }
table.vk td { padding: 4px 8px; }
table.vk td:nth-child(2), table.vk td:nth-child(3) { white-space: nowrap; color: var(--muted); }
@media (max-width: 640px) { table.vk td:nth-child(3) { display: none; } td:first-child { width: auto; } }
.warn { border-left: 3px solid #d97706; padding: 2px 10px; margin: 8px 0; }
"""

final_caption = f"~{TODAY:.1f} s"
doc = f"""<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>STT Progress Report</title>
<style>{css}</style></head><body><main>
<h1>On-device speech-to-text: what we gained</h1>
<p class="sub">HardwareOne P4 + G2 glasses, Oct 3-11 2026. Every number below was measured in this project unless marked as an estimate. Version numbers are labels for the test builds, in the order they were made; the firmware's own version did not change.</p>
<table class="vk">{''.join(f'<tr><td><b>{html.escape(v)}</b></td><td>{html.escape(when)}</td><td>{html.escape(b)}</td><td>{html.escape(t)}</td></tr>' for v, when, b, t in VERSIONS)}</table>
<div class="cards">
  <div class="card"><div class="from">Caption delay after you stop talking</div><div class="big">3.6 s &rarr; ~1.0-1.1 s</div><div class="from">1.1 &rarr; 1.3-1.8, P4 mic, quiet room</div></div>
  <div class="card"><div class="from">Short replies ("yeah", "okay")</div><div class="big">3.4-17 s &rarr; ~0.9 s</div><div class="from">no longer wait for the next sentence</div></div>
  <div class="card"><div class="from">Free PSRAM at its lowest, long speech</div><div class="big">1.6 &rarr; 5.4 MB</div><div class="from">1.6 &rarr; 1.7, the 10 s phrase cap</div></div>
  <div class="card"><div class="from">Speaker labels (2.0)</div><div class="big">91% right</div><div class="from">no caption delay added</div></div>
  <div class="card"><div class="from">Invented words on pure noise</div><div class="big">30 &rarr; 9.5 /min</div><div class="from">deployed model vs old model</div></div>
  <div class="card"><div class="from">500-hour training run on the Mac</div><div class="big">33 h &rarr; ~10 h</div><div class="from">same results, 3x faster steps</div></div>
</div>

<h2>1. The model: accuracy and noise</h2>
<h3>Broad error rate on the full test sets (lower is better)</h3>
{broad}
<h3>Words invented on pure background noise (lower is better)</h3>
{phantom}
<p class="foot">The noise-only training clips cut invented words by about 70% at no accuracy cost (general + noise clips: 23.18 vs 23.11). The new data and the 500-hour run gave the deployed model its accuracy edge. The 2e-5 learning rate was the mistake to avoid.</p>

<h2>2. Training speed on the Mac</h2>
<h3>Training throughput (audio seconds processed per second)</h3>
{trainer_deltas}
<h3>One checkpoint scoring pass</h3>
{eval_time}
<h3>Where a 500-hour run's time goes</h3>
{train_parts}
<p class="foot">The cause: one operation (the backward pass of the depthwise convolutions) was very slow on the Mac's GPU. A replacement written in this project gives the same gradients to within a millionth.</p>

<h2>3. Caption delay on the P4</h2>
<h3>End of speech to caption ready (median, P4 mic)</h3>
{caption}
<p class="foot">From 1.3 on, each change saved tens of milliseconds, which is smaller than the spread between sessions (about &plusmn;0.1 s, more for one-session versions). So the medians from 1.4 on move up and down by noise; what each change did is in the per-change chart below, measured clip by clip. 1.4 and 1.8 were run once, so their medians rest on 14-18 phrases.</p>
<h3>Short replies</h3>
{short}
<h3>Longer phrases</h3>
{longer}
<h3>Speech model time per second of audio (median phrase)</h3>
{model_speed}
<h3>Language-model step per phrase (median)</h3>
{lm_step}
<p class="foot">Model time fell about 40% from 1.1 to 1.5 and then stayed flat: 1.6-1.8 changed when the model starts and how much memory it needs, not its speed. The language-model step halved with the new decoder in 1.4; its size (2.5 or 1.6 MB) does not change its speed.</p>
<h3>Long unbroken speech: the 10 s phrase cap (12-17 s utterances)</h3>
{long_speech}
<p class="foot">Medians over the same 14 clips, 3 sessions each. With a 20 s cap a long utterance is transcribed in one piece after you stop; with 10 s the first part is cut and transcribed while you are still talking. For a typical clip that changes little ({CMP_LONG['median_delta']:+.0f} ms), but some finish much sooner (95% range {CMP_LONG['ci95'][0]:+.0f} to {CMP_LONG['ci95'][1]:+.0f} ms). The main gain is memory (section 4).</p>
<h3>Where the time goes, step by step: all phrases</h3>
{stages_all}
<h3>Short replies (same colours)</h3>
{stages_short}
<h3>Longer phrases (same colours)</h3>
{stages_long}
<p class="foot">The model's split by layer type uses each build's own per-layer timing on the chip: 1.4 changed only the language-model decoder, so it uses 1.3's; 1.5 to 1.8 share one model build, timed in the 1.8 test sessions. 1.4 and 1.8 were run once (7-18 phrases per bar), so their bars are rougher; 2.0 is not shown because it was tested on conversation recordings, where it matched the same build without speaker labels clip by clip ({CMP_SPK['L_speech']['all']['median_delta']:+.0f} ms). Each bar starts when you stop talking and ends when the caption is ready, and the pieces are in the order they happen. Each bar is the average of the middle half of that group's phrases (so one odd phrase cannot skew it), so totals sit close to the medians above. With the head start, the model runs while the end-of-phrase wait is still going, so the grey wait mostly disappears; the light grey piece is the 200 ms of quiet the P4 needs before it starts. The model's split by layer type comes from each version's own per-layer timing on the chip (1.1: an older build of the same model).</p>
<h3>Inside the model run, by layer type (a 5-second phrase)</h3>
{layers}
<p class="foot">Numbers in brackets are how many layers of that type the model has. Depthwise layers are 9% of the model's arithmetic but took about a third of its time: each step read more data than the chip's 64 KB fast cache holds. Working in 64-channel blocks and splitting the channels across both cores fixed that, with bit-identical output. 1.5's prepared layer setups took a further {(sum(LAYERS['today'].values()) - sum(LAYERS['c12'].values())) * 1000:.0f} ms off, mostly in the smaller layers, where setup is a larger share; the 512-wide pointwise layers are now 60% of the run. *1.1's split comes from an older per-layer profile of the same model.</p>
<h3>What each change did (compared one at a time)</h3>
{device_deltas}
<p class="foot">The chip has no neural-net accelerator; its SIMD units were mostly waiting on memory. That is why the cache line was the biggest early win, and why using both cores only paid off once each core worked on its own channels. The last five rows were measured on fixed test audio (model time) or, for short replies, in speaker sessions.</p>


<h2>3b. Through the G2 glasses (Bluetooth)</h2>
<p>With the glasses, the speech engine on the P4 is the same; Bluetooth adds the trip in (mic audio) and the trip out (the caption). Green boxes are the parts this work changed.</p>
{g2_pipe}
<h3>End of speech to caption on the glasses (longer phrases)</h3>
{g2_time}
<h3>Short replies ("yeah", "okay")</h3>
{g2_short}
<p class="foot">Measured: speech processing (P4, same engine as with the glasses), the caption timer (0-200 ms, about 0.11 s on average; from 1.2 on the sender wakes as soon as a caption is ready) and the caption write to the glasses with its acknowledgement (30-102 ms). Estimated: the mic audio trip over Bluetooth (packets every 50 ms plus radio transfer; not measured directly) and the glasses' own drawing time (not included). From 1.2 on the end-of-phrase wait and the processing overlap (the final starts early), so they are one blue bar. With the glasses 1.2 should land at about {BD['b6-c3xn/longer']['median_L'] + 0.15:.1f} s for longer phrases and 1.3 at about {BD['b9-c4an/longer']['median_L'] + 0.15:.1f} s (short replies about {BD['b9-c4an/short']['median_L'] + 0.15:.1f} s), and 1.4-1.8 at about {min(BD[f'v{v}/longer']['median_L'] for v in LATER) + 0.15:.1f}-{max(BD[f'v{v}/longer']['median_L'] for v in LATER) + 0.15:.1f} s (short replies {min(BD[f'v{v}/short']['median_L'] for v in LATER) + 0.15:.1f}-{max(BD[f'v{v}/short']['median_L'] for v in LATER) + 0.15:.1f} s), against about {BD['e0n/longer']['median_L'] + 0.26:.1f} s; none of them has been timed on the glasses yet. 2.0 is not shown: its speaker labels add nothing to the caption path (section 6), so it behaves like 1.8. Earlier glasses logs reported 3.6-5.5 s because up to ~1 s of that was a clock offset in the glasses' audio stream, not real delay.</p>

<h2>4. Memory and accuracy by version</h2>
<h3>Lowest free PSRAM during a session (standard playlist)</h3>
{psram_low}
<h3>Lowest free PSRAM on long unbroken speech</h3>
{psram_long}
<p class="foot">Out of 32 MB. 1.1 rebuilt the model for every phrase, so it held less between phrases. From 1.2 the model and its working area stay for the session (about 2.6 MB more). 1.7 halves the five session audio buffers and the feature caches: 2.7 MB more free after warm-up, and 3.8 MB more at the lowest point on long speech, where phrases used to reach 20 s. 1.8's smaller LM gives back 0.9 MB. 2.0's speaker model takes 3.4 MB: with the 1.6 MB LM about 3 MB stays free at the lowest point.</p>
<h3>Lowest free internal RAM during a session</h3>
{internal_low}
<p class="foot">Internal RAM is the scarce kind (about 260-280 KB free at boot). 1.1 dipped to about 44 KB while it rebuilt the model for each phrase; from 1.2 the model is built once and its bookkeeping is requested from PSRAM. From test batch 17 on (during 1.6's tests) the same firmware booted with about 17 KB more free internal RAM, so the step to ~140 KB is a test-setup change, not the 10 s cap; compare versions within a batch. In the same batch, 2.0's speaker labels lower the low point by 6-11 KB (about 144 &rarr; 134 KB), set while ESP-DL builds the speaker model at session start.</p>
<h3>Word errors, scored clip by clip (standard playlist, lower is better)</h3>
{accuracy}
<p class="foot">Clips whose console text line was lost in any of that version's sessions are left out (a test-harness fault, not the firmware), so each version is scored on 21-26 of the 27 clips. Every version lands between 18.2% and 20.1%; sessions of the same build vary by about &plusmn;2 points. The speed changes are bit-identical on fixed test audio, so their text cannot change; the changes that alter what the model hears (1.2's early final and short-reply rule, 1.7's cut at 10 s) show no clear accuracy cost here. The one change that did cost accuracy, the 100 ms tail, was rejected.</p>

<h2>5. The language model (1.8)</h2>
<h3>Everyday speech: word errors by LM size (P4 recordings re-decoded on the Mac)</h3>
{lm_sizes}
<h3>Tech speech: 180 synthesized sentences (word errors; right column: unknown words recognised)</h3>
{lm_tech}
<p class="foot">The P4 logged each caption's raw speech-model output, and the Mac re-ran the device's exact decoder on it (it reproduces every device caption), so every LM was compared on identical audio. The LM is worth about 3 points; its size barely matters, because the speech model gets most words right on its own and the LM mainly breaks ties that depend on common word pairs, which every size keeps. Decode time is set by the speech, not by memory or the session's load, and is the same for every size. The tech term list doubles the unknown words recognised (8 &rarr; 16 of 126), but most tech words still fail: the speech model has never heard them and spells them by sound. The next training run adds synthesized tech speech to fix that at the source.</p>

<h2>6. Speaker labels (1.9, 2.0)</h2>
<p>Each finished phrase gets a session label, and saved transcript lines read "[Person N] text". The model (clova Fast ResNet-34, 1.4 M weights, 8-bit weights with 16-bit activations) turns a phrase into a voiceprint; phrases join the closest voice heard so far, or start a new one. A different speaker model can be dropped onto the card without new firmware.</p>
<h3>Phrases labelled with the right person</h3>
{spk_acc}
<h3>Labelling time per phrase</h3>
{spk_time}
<p class="foot">Device accuracy is from the four known-speaker conversations (2, 4, 3 and 3 people); repeat runs in the background build landed at 76-85% per conversation, within the run-to-run spread, and the device's voiceprints match the Mac's (cosine 0.997). Two similar audiobook readers merged into one person: their voiceprints are too close for any threshold, a limit of this small model. Turns under 2 s never start a new person. In 2.0, captions did not wait at all: matched clip by clip against the same build without labels, speech end to caption changed by {CMP_SPK['L_speech']['all']['median_delta']:+.0f} ms (95% range {CMP_SPK['L_speech']['all']['ci95'][0]:+.0f} to {CMP_SPK['L_speech']['all']['ci95'][1]:+.0f} ms). Labels reach the transcript 0.8-1.9 s after the caption (median); every saved line got its label, in order. Costs: 3.4 MB of PSRAM, about 110 KB of flash, about 0.5 s at session start, and 6-11 KB of internal RAM at the low point. The 3x3 layers of the speaker model got their own cache-sized blocking in ESP-DL (195 &rarr; 39 ms each, bit-identical).</p>

<h2>7. Trade-offs still open</h2>
<p class="warn"><b>Accuracy:</b> the 1.3 report flagged about 2.5 points more word errors for 1.2 (18.2% &rarr; 20.5% in raw session averages). Scored clip by clip with lost console lines left out, 1.1 to 1.8 all land between 18.2% and 20.1%, so that loss does not reproduce. Tech words are the clear weak spot (about 50% errors on tech sentences); the next training run targets them.</p>
<p class="warn"><b>Memory:</b> correction to the 1.3 report: 1.1's internal RAM fell to about 44 KB during each phrase's model rebuild, not 117 KB; from 1.2 the low point is about 112-117 KB (about 143 KB in later test batches). The speaker model's load at session start lowers it by 6-11 KB; moving ESP-DL's short-lived build buffers to PSRAM explicitly would win that back. A 256 KB cache was measured 11-22% faster but costs 131 KB of internal RAM, so it was rejected for excessive RAM consumption; the cache stays at 128 KB.</p>
<p class="warn"><b>Speaker labels:</b> similar voices can merge (a whole-conversation relabelling pass or a larger model would help, if memory allows); overlapping speech gets one label.</p>
<p class="warn"><b>Not used yet:</b> the faster memory clock (-68 ms) needs a long stability test first. Not yet timed on the glasses themselves. 1.4-2.0 ran in test builds; the stt-speedups branch carries all of it but has not run on the P4 as a whole yet (planned for 0.99.98, after the 15x5 switch).</p>

<h2>8. How it went</h2>
<table>{''.join(f'<tr><td>{html.escape(d)}</td><td>{html.escape(t)}</td></tr>' for d, t in timeline)}</table>
</main></body></html>"""
OUT.write_text(doc)
print(OUT)
