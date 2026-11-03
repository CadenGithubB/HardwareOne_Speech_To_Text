"""Speech-end-to-caption latency against the manifest's true speech ends (segmentation independent).
usage: truelag.py MANIFEST RUN_DIR [RUN_DIR...]
Per clip: the segment holding the clip's speech end (a0 <= end < a1, device ms; the stream clock is
recovered from TL boundary start= samples). close = a1 - end (how long the segmenter waited),
final = pub - end (final caption), ve = trim voiced end - end (how far the trim's voiced end runs
past the true end). Clips whose end falls in no segment are counted as missed."""
import json, re, sys, glob, statistics as st

def kv(line):
    return {k: int(v) for k, v in re.findall(r'\b([a-z_0-9]+)=(-?\d+)\b', line)}

clips = json.load(open(sys.argv[1]))['clips']
def med(v): return int(st.median(v)) if v else None
def p90(v):
    v = sorted(v)
    return int(v[min(len(v) - 1, int(0.9 * (len(v) - 1) + 0.5))]) if v else None
for d in sys.argv[2:]:
    close, final, ve, missed, perrun, longc, shortc = [], [], [], 0, [], [], []
    for f in sorted(glob.glob(d + '/serial-*.log')):
        seg, trim, pub, cap0 = {}, {}, {}, None
        for line in open(f, errors='replace'):
            m = re.search(r'TL (seg|trim seg|pub seq|boundary seg)=(\d+)(.*)', line)
            if not m: continue
            tag, n, v = m.group(1), int(m.group(2)), kv(m.group(3))
            if tag == 'seg': seg[n] = v
            elif tag == 'trim seg': trim[n] = v
            elif tag == 'pub seq': pub[n] = v['t']
            elif tag == 'boundary seg': seg.setdefault(-n - 1, v)  # start sample kept apart
        for n, s in seg.items():
            b = seg.get(-n - 1)
            if n >= 0 and b and 'a0' in s and 'start' in b:
                cap0 = s['a0'] - b['start'] // 16
                break
        if cap0 is None: continue
        runf = []
        for c in clips:
            end = cap0 + int(float(c['speech_end_s']) * 1000)
            hit = [n for n, s in seg.items() if n >= 0 and 'a1' in s and s['a0'] <= end < s['a1'] + 1]
            if not hit or hit[0] not in pub:
                missed += 1; continue
            n = hit[0]; s = seg[n]
            close.append(s['a1'] - end); final.append(pub[n] - end); runf.append(pub[n] - end)
            (longc if s['a1'] - s['a0'] >= 4000 else shortc).append(pub[n] - end)
            if n in trim: ve.append(s['a0'] + trim[n]['voiced_end'] // 16 - end)
        perrun.append(med(runf))
    print('%-40s clips=%d missed=%d | wait-to-close med %s | final med %s p90 %s | long(>=4s) %s short %s | trim ve past end %s | per-run final %s' % (
        d.rstrip('/').split('/')[-1], len(final), missed, med(close), med(final), p90(final), med(longc), med(shortc), med(ve), perrun))
