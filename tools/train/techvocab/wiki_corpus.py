#!/usr/bin/env python3
"""Wikipedia plain text -> spoken-form sentences for an LM component (written text, low weight).

  wiki_corpus.py               reads wiki_text/*.txt and terms.tsv, writes wiki_spoken.txt + wiki_report.json

Per article: everything from References / External links / See also / Notes / Further reading on is dropped.
Sentences of 4-40 words are kept. Written forms become what a speaker says, so the LM sees the same word
sequences the acoustic model produces:
  1. the term list's written forms (longest match, up to 4 tokens; exact case first) -> its spoken form;
  2. all-caps acronyms -> spaced letters, unless the list says the acronym is said as a word;
  3. letter+digit tokens (ESP32, RTX4090, 5G) -> letters + number words; 4-digit numbers read in pairs;
  4. decimals -> "point", units after numbers -> words, & + # -> and plus sharp;
  5. the training normalize_text (lowercase a-z, apostrophes, single spaces).
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lm'))
import hw1lm  # noqa: E402

ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen ' \
       'seventeen eighteen nineteen'.split()
TENS = 'zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()
UNITS = {'GHz': 'gigahertz', 'MHz': 'megahertz', 'kHz': 'kilohertz', 'Hz': 'hertz', 'nm': 'nanometer',
         'GB': 'gigabytes', 'MB': 'megabytes', 'TB': 'terabytes', 'KB': 'kilobytes', 'kB': 'kilobytes',
         'mAh': 'milliamp hours', 'Wh': 'watt hours', 'W': 'watts', 'kW': 'kilowatts', 'V': 'volts', 'mV': 'millivolts',
         'mA': 'milliamps', 'A': 'amps', 'mm': 'millimeters', 'cm': 'centimeters', 'ms': 'milliseconds',
         'fps': 'f p s', 'Mbps': 'megabits per second', 'Gbps': 'gigabits per second', 'dB': 'd b', '%': 'percent',
         'K': 'k', 'p': 'p', 'x': 'x'}
STOP_SECTIONS = re.compile(r'^==+\s*(References|External links|See also|Notes|Further reading|Bibliography|Sources|'
                           r'Citations|Footnotes)\s*==+', re.M)


def below_100(n):
    if n < 20:
        return ONES[n]
    return TENS[n // 10] + ('' if n % 10 == 0 else ' ' + ONES[n % 10])


def cardinal(n):
    if n < 100:
        return below_100(n)
    if n < 1000:
        return ONES[n // 100] + ' hundred' + ('' if n % 100 == 0 else ' ' + below_100(n % 100))
    for div, name in ((10**9, 'billion'), (10**6, 'million'), (1000, 'thousand')):
        if n >= div:
            rest = n % div
            return cardinal(n // div) + ' ' + name + ('' if rest == 0 else ' ' + cardinal(rest))
    return str(n)


def pairs(n):
    """4-digit reading: years and model numbers (4090 -> forty ninety, 2005 -> two thousand five)."""
    hi, lo = divmod(n, 100)
    if lo == 0:
        return cardinal(n) if hi % 10 == 0 else below_100(hi) + ' hundred'
    if 2000 <= n <= 2009:
        return cardinal(n)
    return below_100(hi) + ' ' + ('oh ' + ONES[lo] if lo < 10 else below_100(lo))


def number_words(digits, attached=False):
    n = int(digits)
    if len(digits) > 1 and digits.startswith('0'):
        return ' '.join(ONES[int(d)] for d in digits)
    if len(digits) == 4 and n >= 1000:
        return pairs(n)
    if attached and len(digits) == 3 and n % 100:
        return ONES[n // 100] + ' ' + (('oh ' + ONES[n % 100]) if n % 100 < 10 else below_100(n % 100))
    return cardinal(n)


def load_terms():
    exact, lower, word_acr = {}, {}, set()
    for line in open(HERE / 'terms.tsv', encoding='utf-8'):
        display, spoken = line.rstrip('\n').split('\t')[:2]
        key = tuple(display.split())
        if 1 <= len(key) <= 4:
            exact.setdefault(key, spoken)
            lower.setdefault(tuple(t.lower() for t in key), spoken)
        if re.fullmatch(r'[A-Z]{2,6}', display) and ' ' not in spoken:
            word_acr.add(display)
    return exact, lower, word_acr


def acronym(tok, word_acr):
    plural = tok.endswith('s') and tok[:-1].isupper() and len(tok) > 2
    core = tok[:-1] if plural else tok
    spoken = core.lower() if core in word_acr else ' '.join(core.lower())
    return spoken + (' s' if plural and core not in word_acr else ('s' if plural else ''))


def convert_token(tok, word_acr):
    if re.fullmatch(r'\d+(\.\d+)?', tok):
        if '.' in tok:
            a, b = tok.split('.')
            return number_words(a) + ' point ' + ' '.join(ONES[int(d)] for d in b)
        return number_words(tok)
    m = re.fullmatch(r'(\d+(?:\.\d+)?)([A-Za-z%]+)', tok)          # 5G, 120Hz, 4K, 600W
    if m and m.group(2) in UNITS:
        return convert_token(m.group(1), word_acr) + ' ' + UNITS[m.group(2)]
    if re.fullmatch(r'[A-Z]{2,6}s?', tok) and not re.fullmatch(r'[A-Z][a-z]+', tok):
        return acronym(tok, word_acr)
    if re.search(r'\d', tok) and re.fullmatch(r'[A-Za-z0-9]+', tok):  # ESP32, RTX4090, M2, A17
        out = []
        for run in re.findall(r'[A-Za-z]+|\d+', tok):
            if run.isdigit():
                out.append(number_words(run, attached=True))
            elif run.isupper() and len(run) <= 6:
                out.append(acronym(run, word_acr) if len(run) > 1 else run.lower())
            else:
                out.append(run.lower())
        return ' '.join(out)
    tok = re.sub(r'(?<=[A-Za-z])\+\+', ' plus plus', tok)
    tok = re.sub(r'(?<=\b[A-Fa-f])#', ' sharp', tok)
    tok = tok.replace('&', ' and ').replace('+', ' plus ')
    tok = re.sub(r'\.(js|ts|py|io|ai|net|com|org)\b', lambda m: ' ' + (' '.join(m.group(1)) if m.group(1) in ('js', 'ts', 'py', 'io') else 'dot ' + m.group(1)), tok)
    return tok


def spoken_sentence(sent, exact, lower, word_acr):
    toks = sent.split()
    out, i = [], 0
    while i < len(toks):
        hit = None
        for n in (4, 3, 2, 1):
            if i + n > len(toks):
                continue
            span = [re.sub(r'^[\("\'\[]+|[\)"\'\],;:.!?]+$', '', t) for t in toks[i:i + n]]
            key = tuple(span)
            if key in exact:
                hit = exact[key]
            elif tuple(t.lower() for t in key) in lower and n > 1:
                hit = lower[tuple(t.lower() for t in key)]
            if hit:
                out.append(hit)
                i += n
                break
        if hit:
            continue
        t = re.sub(r'^[\("\'\[]+|[\)"\'\],;:.!?]+$', '', toks[i])
        parts = re.split(r'(?<=[A-Za-z0-9])[-/](?=[A-Za-z0-9])', t)
        out.extend(convert_token(p, word_acr) for p in parts)
        i += 1
    return hw1lm.normalize_text(' '.join(out))


def main():
    exact, lower, word_acr = load_terms()
    n_art = n_sent = n_words = 0
    with open(HERE / 'wiki_spoken.txt', 'w') as f:
        bodies = [p.read_text(errors='replace') for p in sorted((HERE / 'wiki_text').glob('*.txt'))]
        if (HERE / 'intros.jsonl').exists():
            bodies += [json.loads(l)['text'] for l in open(HERE / 'intros.jsonl')]
        for body in bodies:
            m = STOP_SECTIONS.search(body)
            if m:
                body = body[:m.start()]
            body = re.sub(r'^==+.*?==+\s*$', ' ', body, flags=re.M)
            body = re.sub(r'\([^()]{0,200}\)', ' ', body)          # parentheticals (dates, IPA, abbreviations)
            body = re.sub(r'\s+', ' ', body)
            if not body.strip():
                continue
            n_art += 1
            for sent in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"])', body):
                s = spoken_sentence(sent, exact, lower, word_acr)
                w = len(s.split())
                if 4 <= w <= 40:
                    f.write(s + '\n')
                    n_sent += 1
                    n_words += w
    rep = {'articles': n_art, 'sentences': n_sent, 'words': n_words, 'word_acronyms': len(word_acr)}
    (HERE / 'wiki_report.json').write_text(json.dumps(rep, indent=1))
    print(rep)


if __name__ == '__main__':
    main()
