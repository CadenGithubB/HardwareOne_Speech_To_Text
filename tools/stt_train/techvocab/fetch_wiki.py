#!/usr/bin/env python3
"""Open-licence technology text for the LM vocabulary work (user-approved 2026-10-11; Audio Drive only).

  fetch_wiki.py classes      Wikipedia pageprops -> Wikidata class ids for the class articles below
  fetch_wiki.py names        Wikidata query service: well-known items of those classes (CC0) -> names.tsv
  fetch_wiki.py text [MB]    Wikipedia plain text (CC BY-SA) of the most-linked items' articles, capped (default 50 MB)

Sequential, one request at a time with pauses, maxlag honoured; resumable (text/ keeps finished pages).
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
UA = {'User-Agent': 'HW1-STT-vocab/0.1 (personal speech-recognition vocabulary research; sequential, low volume)'}
WP = 'https://en.wikipedia.org/w/api.php'
WDQS = 'https://query.wikidata.org/sparql'

# Wikipedia article whose Wikidata item is the class; items are instances of it (or of a subclass).
CLASS_ARTICLES = {
    'company': ['Technology company', 'Software company', 'Video game developer', 'Fabless manufacturing',
                'Semiconductor industry', 'Telecommunications company', 'Internet company', 'Consumer electronics',
                'Electronics industry', 'Cybersecurity'],
    'product': ['Smartphone', 'Mobile phone', 'Laptop', 'Tablet computer', 'Video game console', 'Handheld game console',
                'Smartwatch', 'Single-board computer', 'Virtual reality headset', 'Smartglasses', 'Wireless earbuds',
                'Drone', 'Digital camera', 'Smart speaker', 'Graphics card', '3D printer'],
    'hardware': ['Microcontroller', 'Microprocessor', 'System on a chip', 'Graphics processing unit', 'Instruction set architecture',
                 'Computer bus', 'Electronic component', 'Sensor', 'Computer memory', 'Field-programmable gate array'],
    'software': ['Operating system', 'Linux distribution', 'Mobile app', 'Web browser', 'Application software', 'Web service',
                 'Cloud computing', 'Social networking service', 'Video game engine', 'Integrated development environment',
                 'File format', 'Audio codec', 'Video codec', 'Free and open-source software'],
    'dev_ai': ['Programming language', 'Software framework', 'Web framework', 'Library (computing)', 'Database',
               'Large language model', 'Machine learning', 'Version control'],
    'net': ['Communication protocol', 'Network protocol', 'Wireless network', 'Technical standard', 'Computer port (hardware)'],
}


# Classes whose Wikidata members are mostly not technology (Wikipedias, time zones, telescopes, ...).
JUNK_CLASSES = {'Database', 'Technical standard', 'Web service', 'Sensor', 'Computer port (hardware)',
                'Free and open-source software', 'Cloud computing', 'Machine learning', 'Version control'}


def get(url, params, tries=6):
    q = urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(f'{url}?{q}', headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            wait = int(e.headers.get('Retry-After', '0') or 0) or 10 * (i + 1)
            print(f'  HTTP {e.code}; waiting {wait} s', flush=True)
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001
            print(f'  {type(e).__name__}; retry', flush=True)
            time.sleep(5 * (i + 1))
    raise SystemExit(f'giving up on {url}')


def classes():
    out = {}
    for group, titles in CLASS_ARTICLES.items():
        r = get(WP, {'action': 'query', 'prop': 'pageprops', 'ppprop': 'wikibase_item', 'redirects': 1,
                     'titles': '|'.join(titles), 'format': 'json', 'maxlag': 5})
        for p in r['query']['pages'].values():
            qid = p.get('pageprops', {}).get('wikibase_item')
            if qid:
                out.setdefault(group, []).append({'title': p['title'], 'qid': qid})
        time.sleep(1)
    (HERE / 'classes.json').write_text(json.dumps(out, indent=1))
    for g, v in out.items():
        print(g, [(c['title'], c['qid']) for c in v])


def names():
    cls = json.loads((HERE / 'classes.json').read_text())
    rows, seen = [], set()
    for group, items in cls.items():
        for c in items:
            # instances of the class or of its subclasses, with an English label and an enwiki page, popular first
            # companies: anything whose industry (P452) is the class; others: instances (P31/P279*)
            match = f'wdt:P452 wd:{c["qid"]}' if group == 'company' else f'wdt:P31/wdt:P279* wd:{c["qid"]}'
            q = f'''SELECT ?item ?label ?title ?links WHERE {{
  ?item {match} ; wikibase:sitelinks ?links ; rdfs:label ?label .
  FILTER(LANG(?label) = "en") FILTER(?links >= 8)
  OPTIONAL {{ ?art schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title . }}
}} ORDER BY DESC(?links) LIMIT 2500'''
            try:
                r = get(WDQS, {'query': q, 'format': 'json'})
            except SystemExit:
                print(f'{c["title"]}: query failed, skipped', flush=True)
                continue
            n = 0
            for b in r['results']['bindings']:
                qid = b['item']['value'].rsplit('/', 1)[-1]
                if qid in seen:
                    continue
                seen.add(qid)
                rows.append((group, c['title'], qid, b['label']['value'], b.get('title', {}).get('value', ''),
                             int(b['links']['value'])))
                n += 1
            print(f'{group:9s} {c["title"]:35s} {n:5d} new items', flush=True)
            time.sleep(2)
    with open(HERE / 'names.tsv', 'w') as f:
        for r in rows:
            f.write('\t'.join(map(str, r)) + '\n')
    print(f'{len(rows)} items -> names.tsv')


def text(cap_mb):
    """Article introductions, 20 per request (Wikipedia throttles unidentified clients: one request at a time,
    a pause between, Retry-After honoured). Resumable: intros.jsonl keeps every finished title."""
    rows = [r for r in (l.rstrip('\n').split('\t') for l in open(HERE / 'names.tsv')) if r[1] not in JUNK_CLASSES]
    titles = [t for _, t in sorted({(int(r[5]), r[4]) for r in rows if r[4]}, reverse=True)]
    core = ['Technology company', 'Smartphone', 'Microcontroller', 'Programming language', 'Large language model',
            'Bluetooth', 'Wi-Fi', 'Raspberry Pi', 'Arduino', 'ESP32', 'Graphics processing unit', 'Cloud computing',
            'Smartglasses', 'Firmware', 'Embedded system', 'Printed circuit board', 'Machine learning']
    titles = core + [t for t in titles if t not in core]
    out = HERE / 'intros.jsonl'
    done, total = set(), 0
    if out.exists():
        for l in open(out):
            d = json.loads(l); done.add(d['title']); total += len(d['text'].encode())
    todo = [t for t in titles if t not in done]
    with open(out, 'a') as f:
        for i in range(0, len(todo), 20):
            if total >= cap_mb * 1e6:
                break
            batch = todo[i:i + 20]
            r = get(WP, {'action': 'query', 'prop': 'extracts', 'exintro': 1, 'explaintext': 1, 'exlimit': 20,
                         'redirects': 1, 'titles': '|'.join(batch), 'format': 'json', 'maxlag': 5})
            for page in r.get('query', {}).get('pages', {}).values():
                body = page.get('extract') or ''
                f.write(json.dumps({'title': page.get('title', ''), 'text': body}) + '\n')
                total += len(body.encode())
            f.flush()
            done.update(batch)
            if (i // 20) % 10 == 0:
                print(f'{len(done)} titles, {total / 1e6:.1f} MB', flush=True)
            time.sleep(4)
    print(f'done: {len(done)} titles, {total / 1e6:.1f} MB')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'classes':
        classes()
    elif cmd == 'names':
        names()
    elif cmd == 'text':
        text(float(sys.argv[2]) if len(sys.argv) > 2 else 50)
