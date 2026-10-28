"""Independent letters-and-digits check: imports nothing from build.py or check_repo.py.

    python -X utf8 scripts/mongolia-law/check_letters.py C:/Users/alany/Documents/mongolia-law

For every law version in the repo (every commit with Kind: original or consolidated), the letters and digits of its
files, in index.txt order, must equal the letters and digits of the raw page's tab (tab "bordered-tab1" for the current
text, "active-tab-10" for the original), sliced here by element ids, with tags, scripts and the site's UI labels removed.
"""
import gzip, html, re, subprocess, sys, unicodedata
from pathlib import Path

CACHE = Path(__file__).parent / '.cache'
UI = ['Сонсох / Сонгосон утга сонсох', 'Хуваалцах', 'Текст томруулах', 'Хэвлэх', 'Pdf', 'Word']
SUP = str.maketrans('\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079', '0123456789')


def ld(s: str) -> str:
    s = unicodedata.normalize('NFC', s).translate(SUP)
    return ''.join(c for c in s if c.isalnum()).lower()


def tab(page: str, tid: str) -> str:
    a = page.find(f'id="{tid}"')
    if a < 0:
        return ''
    a = page.find('>', a) + 1  # after the tab's own opening tag
    nxt = re.search(r'<[a-z]+[^>]* id="(?:active-tab-\d+|bordered-tab\d+)"|<div class="tw-fixed"', page[a:])
    s = page[a:a + nxt.start()] if nxt else page[a:]
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>|<!--.*?-->', ' ', s)
    # a tag name starts with an ASCII letter (HTML rules): the site's literal "<д>, <е>" stay text
    s = re.sub(r'(?s)<[/!]?[A-Za-z](?:[^>"\']|"[^"]*"|\'[^\']*\')*>', ' ', s)
    s = html.unescape(s)
    for u in UI:
        s = s.replace(u, ' ')
    s = re.sub(r'^\s*A\s+A\s+A\b', ' ', s)  # the three "A" font-size buttons, at the top of the tab only
    s = re.sub(r'\$focusId.*?\}\s*\}', ' ', s, flags=re.S)
    return ld(s)


def main():
    repo = sys.argv[1]
    g = lambda *a: subprocess.run(['git', '-C', repo, *a], capture_output=True, check=True).stdout
    cat = subprocess.Popen(['git', '-C', repo, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    def blob(spec):
        cat.stdin.write(spec.encode() + b'\n'); cat.stdin.flush()
        h = cat.stdout.readline().split()
        if h[1] == b'missing':
            return None
        d = cat.stdout.read(int(h[2])); cat.stdout.read(1); return d.decode('utf-8')
    log = g('log', '--all', '--format=%H%x1f%B%x1e').decode('utf-8')
    n = bad = 0
    for rec in log.split('\x1e'):
        if not rec.strip():
            continue
        h, body = rec.strip('\n').split('\x1f', 1)
        kind = re.search(r'^Kind: (\w+)', body, re.M)
        if not kind or kind.group(1) not in ('original', 'consolidated'):
            continue
        lid = re.search(r'^Law-id: (\d+)$', body, re.M).group(1)
        folder = 'undsen-khuuli' if lid == '367' else f'huuli/{lid}'
        page = gzip.decompress((CACHE / 'doc' / f'{lid}.html.gz').read_bytes()).decode('utf-8', 'replace')
        orig = kind.group(1) == 'original' and 'current text taken as adopted' not in body
        want = tab(page, 'active-tab-10' if orig else 'bordered-tab1')
        got = ld(''.join(blob(f'{h}:{folder}/{f}') for f in blob(f'{h}:{folder}/index.txt').split()))
        n += 1
        if got != want:
            bad += 1
            i = next((k for k in range(min(len(got), len(want))) if got[k] != want[k]), min(len(got), len(want)))
            if bad <= 15:
                print(folder, h[:9], kind.group(1), len(got), len(want), 'repo', got[i:i+40], '| site', want[i:i+40])
    print(f'versions {n}, letters-and-digits mismatches {bad}')
    (CACHE / 'letters.txt').write_text(f'{n} versions, {bad} mismatches\n', 'utf-8')
    sys.exit(1 if bad else 0)


main()
