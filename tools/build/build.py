"""Build the Mongolia law repository from the legalinfo.mn cache (fetch.py).

    python -X utf8 scripts/mongolia-law/build.py ~/Documents/mongolia-law --today YYYY-MM-DD [--limit N] [--workers N]

legalinfo.mn (Эрх зүйн мэдээллийн нэгдсэн систем) publishes the CURRENT consolidated text of each law, for a few laws
also the ORIGINAL text ("Анхны эх"), and the list of amending acts with their adoption dates. It keeps no dated
versions in between, so this is a current-only corpus ("history": "current-only"):

1. Each law is one folder, `huuli/<lawId>/` (the site's own law id; the Constitution is `undsen-khuuli/`). Each article
   ("1 дүгээр зүйл", "Арван есдүгээр зүйл") is one file, `zuil-1.md`, `zuil-19-1.md` for "Арван ес\u00b9 дүгээр зүйл", one
   paragraph per line. What stands before the first article (title, date, place, preamble) is `ehlel.md`; chapter
   headings in capitals that stand right before an article go on top of that article's file; `index.txt` gives the
   reading order. Text is exactly as published (Mongolian, Cyrillic); only whitespace is normalised, soft hyphens are
   dropped and <sup> digits become superscript digits.
2. Commits, per law:
   - ORIGINAL: if the site has the original text, one commit with it, dated noon Ulaanbaatar time on the law's own
     in-force date ("дагаж мөрдөх огноо"), authored by the law.
   - UNAMENDED: if the site lists no amending act and has no original text, the current text is the text as adopted:
     one commit on the in-force date, authored by the law, with an Evidence: trailer saying so.
   - CURRENT: otherwise, one commit with the current text, dated the retrieval day, authored by the publisher, with one
     Amended-by: trailer per amending act (adoption date, title, site id). Its In-force: is the retrieval day: the text
     as in force that day. Unknown-from: gives the first amending act's adoption date, from which the wording on any
     earlier-dated commit may no longer be the law (tools/in_force_on.py warns).
   - Laws whose in-force date is after --today go on the `future` branch, never merged.
   The publisher's per-provision notes ("/Энэ хэсгийг 2019 оны ... хуулиар өөрчлөн найруулсан/") stay in the text and
   are listed in data/amendments.csv.
3. One git fast-import stream, everything sorted, so the same cache always gives the same hashes.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
SITE = 'https://legalinfo.mn'
COMMITTER = 'Lexifina <mongolia-law@lexifina.com>'
PUBLISHER = ('Эрх зүйн мэдээллийн '
             'нэгдсэн систем (legalinfo.mn)',
             'consolidation@legalinfo-mn.invalid')
CONSTITUTION = {'lawId': '367', 'title': 'МОНГОЛ УЛСЫН '
                'ҮНДСЭН ХУУЛЬ', 'adopted': '1992-01-13',
                'inforce': '1992-02-12'}  # Art. 70.2: in force from noon on 12 February 1992

# ------------------------------------------------------------------------------------------------ time

def last_weekday(y: int, m: int, wd: int) -> date:
    """Last given weekday (Mon=0) of month m."""
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    while d.weekday() != wd:
        d -= timedelta(days=1)
    return d


def ub_offset(d: date) -> int:
    """Asia/Ulaanbaatar UTC offset in hours at noon on day d (tzdata 'Mongol' rules, hard-coded: no tzdata here).
    +7 before 1978; +8 since, with summer time (+9) in 1983-1998, 2001-2006 and 2015-2016. Noon is never inside a
    transition hour, so the test is start <= day < end."""
    y = d.year
    if y < 1978:
        return 7
    start = end = None
    if y in (1983, 1984):
        start, end = date(y, 4, 1), date(1983, 10, 1) if y == 1983 else last_weekday(1984, 9, 6)
    elif 1985 <= y <= 1998:
        start, end = last_weekday(y, 3, 6), last_weekday(y, 9, 6)
    elif y == 2001:
        start, end = last_weekday(y, 4, 5), last_weekday(y, 9, 5)
    elif 2002 <= y <= 2006:
        start, end = last_weekday(y, 3, 5), last_weekday(y, 9, 5)
    elif y in (2015, 2016):
        start, end = last_weekday(y, 3, 5), last_weekday(y, 9, 5)
    return 9 if start and start <= d < end else 8


def git_date(day: str, seq: int = 0) -> str:
    """Noon in Ulaanbaatar on day; before 1970 (git rejects it) clamp to 1970-01-01, one second apart (seq)."""
    d = date.fromisoformat(day)
    off = ub_offset(d)
    if d < date(1970, 1, 1):
        return f'{seq} +0000'
    ts = int(datetime(d.year, d.month, d.day, 12 - off, 0, tzinfo=timezone.utc).timestamp())
    return f'{ts} +{off:02d}00'

# ------------------------------------------------------------------------------------------------ text

WS = re.compile(r'[\s\u00a0\u2000-\u200a\u202f\u205f\u3000]+')
DROP = re.compile(r'[\u00ad\u200b\u200c\u200d\u2060\ufeff]')
SUP = str.maketrans('0123456789', '\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079')
UNSUP = str.maketrans('\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079', '0123456789')


def norm(s: str) -> str:
    return WS.sub(' ', DROP.sub('', s)).strip()


BLOCK = {'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'blockquote', 'ul', 'ol', 'dl', 'dt', 'dd',
         'center', 'pre', 'address', 'body', 'html', 'section', 'article'}
SKIP = {'style', 'script', 'head', 'title', 'xml', 'noscript', 'button', 'select', 'option'}


class Paras(HTMLParser):
    """HTML -> paragraphs (str). A table row is one paragraph with its cells joined by ' | '."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.cur: list[str] = []
        self.skip = 0
        self.cell = 0
        self.row: list[str] | None = None

    def flush(self):
        t = norm(''.join(self.cur))
        if t == HEAD:  # the heading flag sits just before the heading's own <p>: carry it over
            self.pending = True
            self.cur = []
            return
        if t and getattr(self, 'pending', False):
            t = HEAD + t.lstrip(HEAD)
            self.pending = False
        if self.row is not None and self.cell:
            if t:
                self.row[-1] = (self.row[-1] + ' ' + t).strip()
        elif t:
            self.out.append(t)
        self.cur = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == 'br':
            self.cur.append(' ')
        elif tag == 'tr':
            self.flush()
            self.row = []
        elif tag in ('td', 'th'):
            if self.row is None:
                self.flush()
                self.row = []
            self.flush()
            self.row.append('')
            self.cell += 1
        elif tag in BLOCK:
            self.flush()

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ('td', 'th'):
            self.flush()
            self.cell = max(0, self.cell - 1)
        elif tag == 'tr':
            self.flush()
            cells = self.row or []
            self.row = None
            self.cell = 0
            if any(cells):
                self.out.append(' | '.join(cells))
        elif tag in BLOCK:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)

    def close(self):
        super().close()
        if self.row is not None:
            self.handle_endtag('tr')
        self.flush()


def paras(fragment: str) -> list[str]:
    fragment = re.sub(r'(?is)<sup[^>]*>\s*([0-9]+)\s*</sup>', lambda m: m.group(1).translate(SUP), fragment)
    p = Paras()
    p.feed(fragment)
    p.close()
    return p.out


def current_fragment(page: str) -> str | None:
    """The current text: tab 1 of the law page, from its 'maincontenter' to the next tab, without the per-paragraph
    link icons and their (empty, hidden) cross-reference boxes."""
    a = page.find('id="bordered-tab1"')
    if a < 0:
        return None
    b = page.find('class="maincontenter', a)
    e = page.find('<div class="tab-pane', a + 20)
    e = e if e > 0 else len(page)
    if b < 0 or b > e:
        return None
    s = page[page.rfind('<', 0, b):e]
    s = re.sub(r'(?s)<span class="icon-s"[^>]*>.*?</span>', '', s)
    s = re.sub(r'(?s)<span class="pull-right print-zuil"[^>]*>.*?</span>', '', s)  # the "Хэвлэх" (print) link
    # the site marks chapter headings data-pp="2" (some only look capitalised through CSS): flag them for split()
    s = re.sub(r'(<div class="w-100 pull-left responsive_mobile[^"]*"[^>]*data-pp="2"[^>]*>)', r'\1' + HEAD, s)
    s = re.sub(r'(?s)<p class="\d+[^"]*" style="display:none;[^"]*"></p>', '', s)
    s = re.sub(r'(?s)<div class="nom-more-divider.*?</div>', '', s)
    return s


def original_fragment(page: str) -> str | None:
    """The original text ("Анхны эх"): tab 10, the body inside its '--nomigration' block."""
    a = page.find('id="active-tab-10"')
    if a < 0:
        return None
    b = page.find('--nomigration">', a)
    # ends at the next tab pane (often tab 11, the unofficial English translation) or the page footer
    ends = [x for x in (page.find('<div class="tab-pane', a + 20), page.find('<div class="tw-fixed"', a)) if x > 0]
    e = min(ends) if ends else len(page)
    if b < 0 or b > e:
        return None
    return page[b + len('--nomigration">'):e]


STEMS = {'нэг': 1, 'хоёр': 2, 'гурав': 3,
         'дөрөв': 4, 'тав': 5, 'зурга': 6,
         'зургаа': 6, 'дол': 7, 'долоо': 7,
         'найм': 8, 'ес': 9, 'арав': 10, 'хорь': 20,
         'гуч': 30, 'дөч': 40, 'тавь': 50, 'жар': 60,
         'дал': 70, 'ная': 80, 'ер': 90}
TENS = {'арван': 10, 'хорин': 20, 'гучин': 30,
        'дөчин': 40, 'тавин': 50, 'жаран': 60,
        'далан': 70, 'наян': 80, 'ерэн': 90}
SUPS = '\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079'
ZUIL = 'зүйл'  # зүйл
ORD = '(?:дүгээр|дугаар|дахь|дэх|-?р)'
ART_NUM = re.compile(rf'^(\d{{1,4}}(?:\.\d{{1,4}})?)([{SUPS}]*)\s*(?:{ORD})?\s*{ZUIL}(?=$|[\s.:,])', re.I)
ART_WORD = re.compile(rf'^((?:[А-яЁёӨөҮү]+\s+)?[А-яЁёӨөҮү]+?)'
                      rf'([{SUPS}]*)\s*(?:дүгээр|дугаар)\s+{ZUIL}(?=$|[\s.:,])', re.I)


def word_number(words: str) -> int | None:
    parts = words.lower().split()
    if len(parts) == 1:
        return STEMS.get(parts[0])
    if len(parts) == 2 and parts[0] in TENS and parts[1] in STEMS and STEMS[parts[1]] < 10:
        return TENS[parts[0]] + STEMS[parts[1]]
    return None


def article(line: str) -> str | None:
    """'zuil-<n>[-<sup>]' if the paragraph starts an article, else None."""
    m = ART_NUM.match(line)
    if m:
        n = '.'.join(str(int(x)) for x in m.group(1).split('.'))  # codes number articles 1.1, 1.2, ...
    else:
        m = ART_WORD.match(line)
        if not m:
            return None
        v = word_number(m.group(1))
        if v is None:
            return None
        n = str(v)
    sup = m.group(2).translate(UNSUP)
    return f'zuil-{n}' + (f'-{sup}' if sup else '')


LETTERS = re.compile('[A-Za-z\u0400-\u04ff]')
HEAD = '\ue000'  # private-use flag for a paragraph the site marks as a heading; never in the text itself
CHAPTER = re.compile('(БҮЛЭГ|ХЭСЭГ|бүлэг|хэсэг)')
CAPWORD = re.compile(r'^[А-ЯЁӨҮ]{2,}\.\s')


def heading(line: str) -> bool:
    """A chapter or section heading: flagged by the site, or short and in capitals ("НЭГДҮГЭЭР БҮЛЭГ"), or a section
    title such as "НЭГ. Монгол Улсын Их Хурал"; never an article or a /note/."""
    if line.startswith(HEAD):
        return True
    letters = LETTERS.findall(line)
    if not letters or len(line) >= 250 or article(line) or line.startswith('/'):
        return False
    return all(not c.islower() for c in letters) or (len(line) < 120 and bool(CAPWORD.match(line)))


def split(lines: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    starts = [(i, a) for i, l in enumerate(lines) if (a := article(l))]
    files: dict[str, list[str]] = {}
    order: list[str] = []
    if not starts:
        lines = [l.lstrip(HEAD) for l in lines]
        if lines:
            files['text.md'] = lines
            order.append('text.md')
        return files, order
    bounds = []
    prev = -1
    for k, (i, name) in enumerate(starts):
        j = i
        while j - 1 > prev and heading(lines[j - 1]) and i - (j - 1) <= 6:
            j -= 1
        if k == 0:
            # before the first article only a chapter or part heading moves with it ("НЭГДҮГЭЭР БҮЛЭГ" and its title);
            # the act's own title, date and place stay in ehlel.md
            c = next((x for x in range(j, i) if CHAPTER.search(lines[x])), i)
            j = c
        bounds.append((j, name))
        prev = i
    lines = [l.lstrip(HEAD) for l in lines]
    if bounds[0][0] > 0:
        files['ehlel.md'] = lines[:bounds[0][0]]
        order.append('ehlel.md')
    seen: dict[str, int] = {}
    for k, (j, name) in enumerate(bounds):
        end = bounds[k + 1][0] if k + 1 < len(bounds) else len(lines)
        seen[name] = seen.get(name, 0) + 1
        fn = f'{name}.md' if seen[name] == 1 else f'{name}~{seen[name]}.md'
        files[fn] = lines[j:end]
        order.append(fn)
    return files, order


MONTHS = '(?:дүгээр|дугаар)'
NOTE_DATE = re.compile(rf'(\d{{4}})\s*оны\s+(\d{{1,2}})\s*(?:-?\s*{MONTHS})?\s*сарын\s+(\d{{1,2}})', re.I)
NOTE = re.compile(r'^/(.{10,600})/\.?$')
ACTIONS = [('хүчингүй', 'repealed'), ('өөрчлөн найруул', 'rewritten'),
           ('хассан', 'deleted'), ('нэмсэн', 'added'),
           ('нэмэлт, өөрчлөлт', 'amended'),
           ('нэмэлт', 'supplemented'), ('өөрчлөлт', 'amended'),
           ('дагаж мөрдө', 'applies-from'),
           ('цэц', 'constitutional court'), ('түдгэлзүүл', 'suspended')]


def note_rows(folder: str, files: dict[str, list[str]]) -> list[list[str]]:
    rows = []
    for fn in sorted(files):
        for n, line in enumerate(files[fn], 1):
            m = NOTE.match(line)
            if not m:
                continue
            low = m.group(1).lower()
            d = NOTE_DATE.search(m.group(1))
            day = ''
            if d:
                try:
                    day = date(int(d.group(1)), int(d.group(2)), int(d.group(3))).isoformat()
                except ValueError:
                    day = ''
            kind = next((k for w, k in ACTIONS if w in low), 'note')
            rows.append([folder, fn[:-3], str(n), kind, day, line])
    return rows


def amend_list(law_id: str) -> list[dict]:
    out = []
    pages = sorted(CACHE.glob(f'amend/{law_id}.p*.json.gz'), key=lambda p: int(p.name.split('.p')[1].split('.')[0]))
    first = CACHE / 'amend' / f'{law_id}.json.gz'
    for p in ([first] if first.exists() else []) + pages:
        h = json.loads(gzip.decompress(p.read_bytes()).decode('utf-8'))['Html']
        for m in re.finditer(r'data-id="(\d+)".*?<h6><a[^>]*>(.*?)</a></h6>.*?<span>\s*([0-9-]*)\s*</span>', h, re.S):
            out.append({'id': m.group(1), 'title': norm(re.sub(r'<[^>]+>', '', m.group(2))), 'adopted': m.group(3)[:10]})
    total = 0
    if first.exists():
        t = re.findall(r'Нийт (\d+)', json.loads(gzip.decompress(first.read_bytes()).decode('utf-8'))['Html'])
        total = int(t[0]) if t else 0
    if len(out) != total:
        raise SystemExit(f'amendments of {law_id}: {len(out)} rows, site says {total}')
    return out


def build_law(law: dict) -> dict:
    p = CACHE / 'doc' / f"{law['lawId']}.html.gz"
    res = {'issues': [], 'cur': {}, 'orig': {}, 'notes': [], 'amend': [], 'tables': 0}
    if not p.exists():
        res['issues'].append([law['folder'], 'not fetched'])
        return res
    page = gzip.decompress(p.read_bytes()).decode('utf-8', 'replace')
    try:
        res['amend'] = amend_list(law['lawId'])
    except SystemExit as e:
        res['issues'].append([law['folder'], str(e)])
    frag = current_fragment(page)
    if frag is None:
        res['issues'].append([law['folder'], 'no current text on the page'])
        return res
    res['tables'] = frag.count('<table')
    lines = paras(frag)
    files, order = split(lines)
    if not order:
        res['issues'].append([law['folder'], 'current text is empty'])
        return res
    if 'text.md' in files:
        res['issues'].append([law['folder'], 'no article headings found; whole text in text.md'])
    res['cur'] = {**files, 'index.txt': order}
    res['notes'] = note_rows(law['folder'], files)
    of = original_fragment(page)
    if of is not None:
        olines = paras(of)
        ofiles, oorder = split(olines)
        letters = ''.join(LETTERS.findall(' '.join(olines)))
        latin = sum(1 for c in letters if c < '\u0080')
        if letters and latin > len(letters) / 2:
            res['issues'].append([law['folder'], 'original text tab holds a translation (Latin script); not used'])
        elif oorder:
            res['orig'] = {**ofiles, 'index.txt': oorder}
        else:
            res['issues'].append([law['folder'], 'original text tab is empty'])
    res['annex_tab'] = any('Хавсралт' == ' '.join(re.sub('<[^>]+>', '', m.group(1)).split()) for m in re.finditer(
        r'<a href="#[a-z]+-tab-?\d+"[^>]*class="nav-link[^>]*>(.*?)</a>', page, re.S))  # the "Хавсралт" (annex) tab
    return res


def render(folder: str, files: dict) -> dict[str, bytes]:
    out = {}
    for fn, lines in files.items():
        out[f'{folder}/{fn}'] = ('\n'.join(lines) + '\n').encode('utf-8')
    return out

# ------------------------------------------------------------------------------------------------ laws

def iso_or_blank(s: str) -> str:
    s = (s or '').strip()[:10]
    try:
        return date.fromisoformat(s).isoformat() if s and not s.startswith('0000') else ''
    except ValueError:
        return ''


def load_laws(limit: int | None) -> list[dict]:
    rows = json.loads((CACHE / 'list' / 'laws.json').read_text('utf-8'))
    laws = [{**CONSTITUTION, 'folder': 'undsen-khuuli', 'kind': 'constitution'}]
    for r in rows:
        laws.append({'lawId': r['lawId'], 'title': norm(r['title']), 'adopted': iso_or_blank(r['adopted']),
                     'inforce': iso_or_blank(r['inforce']), 'folder': f"huuli/{r['lawId']}", 'kind': 'law'})
    laws.sort(key=lambda l: (l['kind'] != 'constitution', int(l['lawId'])))
    return laws[:limit] if limit else laws


def short(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 3].rstrip() + '...'


def law_author(law: dict) -> tuple[str, str]:
    name = norm(law['title'])
    if law['adopted']:
        name += f" ({law['adopted']})"
    return name.replace('<', '').replace('>', ''), f"law-{law['lawId']}@legalinfo-mn.invalid"


def plan(laws: list[dict], built: list[dict], retrieved: str, today: str) -> tuple[list, list, list]:
    """(main commits, future commits, issues). A commit is a dict: day, author, kind, law, files, trailers, body."""
    main, future, issues = [], [], []
    for law, b in zip(laws, built):
        issues += b['issues']
        if not b['cur']:
            continue
        start = law['inforce'] or law['adopted']
        start_src = 'in-force date' if law['inforce'] else 'adoption date (no in-force date given)'
        amend = b['amend']
        cur = render(law['folder'], b['cur'])
        orig = render(law['folder'], b['orig']) if b['orig'] else None
        url = f"{SITE}/mn/detail?lawId={law['lawId']}"
        base = [f"Law: {law['title']}", f"Law-id: {law['lawId']}"]
        if law['adopted']:
            base.append(f"Adopted: {law['adopted']}")
        base.append(f'Source: {url}')
        commits = []
        if orig and start:
            commits.append({'day': start, 'author': law_author(law), 'kind': 'original', 'law': law, 'files': orig,
                            'trailers': ['Kind: original', f'In-force: {start}', *base,
                                         *([] if law['inforce'] else ['Evidence: no in-force date given; adoption date used'])],
                            'body': [f"The original text of {law['title']}, as legalinfo.mn shows it under",
                                     f'"Анхны эх" (original text), dated by its {start_src}.']})
        changed = [r for r in b['notes'] if r[3] not in ('note', 'applies-from')]
        if not amend and changed:
            issues.append([law['folder'], f'{len(changed)} amendment notes in the text but no amending act listed; '
                           'not taken as the text as adopted'])
        if not amend and not orig and start and not changed:
            commits.append({'day': start, 'author': law_author(law), 'kind': 'original', 'law': law, 'files': cur,
                            'trailers': ['Kind: original', f'In-force: {start}', *base,
                                         'Evidence: legalinfo.mn lists no amending act; current text taken as adopted',
                                         *([] if law['inforce'] else ['Evidence: no in-force date given; adoption date used'])],
                            'body': [f"The text of {law['title']}, dated by its {start_src}.",
                                     'legalinfo.mn lists no act amending it, so its current text is taken as the text',
                                     'as adopted.']})
        elif not commits or commits[-1]['files'] != cur:
            first = min((a['adopted'] for a in amend if a['adopted']), default='')
            day = retrieved
            if start and start > retrieved:
                day = start  # not yet in force: the current text goes with it on the future branch
            tr = ['Kind: consolidated', f'In-force: {day}', f'Consolidated: {retrieved}', *base]
            for a in sorted(amend, key=lambda a: (a['adopted'], a['id'])):
                tr.append(f"Amended-by: {a['adopted'] or 'undated'} {a['title']} (legalinfo.mn {a['id']})")
            if first and commits:
                tr.append(f'Unknown-from: {first}')
            if not orig:
                tr.append('Original-text: not published on legalinfo.mn')
            body = [f"The current text of {law['title']}, as legalinfo.mn published it on {retrieved}.", '',
                    'legalinfo.mn keeps no dated versions between the original and the current text, so this commit',
                    'is authored by the publisher and no line is credited to an amending act. '
                    f"The site lists {len(amend)} amending act(s)",
                    '(Amended-by:, by adoption date); the per-provision notes in the text are in data/amendments.csv.']
            if commits:
                body += ['', f'The earlier commit holds the original text; from {first or "an unknown date"} it may no '
                         'longer be the law, and the wording in between is not published.']
            elif not orig:
                body += ['', 'legalinfo.mn publishes no original text ("Анхны эх") for this law, so this is its only',
                         'commit: the text before the retrieval day is not in this repository.']
            commits.append({'day': day, 'author': PUBLISHER, 'kind': 'consolidated', 'law': law, 'files': cur,
                            'trailers': tr, 'body': body})
        for c in commits:
            (future if c['day'] > today else main).append(c)
    key = lambda c: (c['day'], c['kind'] != 'original', c['law']['kind'] != 'constitution', int(c['law']['lawId']))
    main.sort(key=key)
    future.sort(key=key)
    return main, future, issues


def message(c: dict) -> str:
    law = c['law']
    what = 'original text' if c['kind'] == 'original' else 'current text'
    subject = short(f"{law['title']}: {what}", 72)
    return '\n'.join([subject, '', *c['body'], '', *c['trailers']]) + '\n'


def fast_import(repo: Path, main: list, future: list, docs: dict[str, bytes], retrieved: str) -> None:
    proc = subprocess.Popen(['git', '-C', str(repo), 'fast-import', '--quiet', '--done'], stdin=subprocess.PIPE)
    w = proc.stdin.write
    mark = 0
    seq = 0

    def commit(ref: str, c: dict | None, files: dict[str, bytes], author: tuple[str, str], day: str, msg: str,
               parent: int | None) -> int:
        nonlocal mark, seq
        mark += 1
        seq += 1
        when = git_date(day, seq)
        w(f'commit {ref}\nmark :{mark}\n'.encode())
        w(f'author {author[0]} <{author[1]}> {when}\ncommitter {COMMITTER} {when}\n'.encode('utf-8'))
        m = msg.encode('utf-8')
        w(f'data {len(m)}\n'.encode() + m + b'\n')
        if parent:
            w(f'from :{parent}\n'.encode())
        if c is not None:
            w(f"D {c['law']['folder']}\n".encode())  # the law's folder is replaced whole: no stale article files
        for path, data in sorted(files.items()):
            w(f'M 100644 inline {path}\ndata {len(data)}\n'.encode('utf-8') + data + b'\n')
        w(b'\n')
        return mark

    last = None
    for c in main:
        last = commit('refs/heads/main', c, c['files'], c['author'], c['day'], message(c), last)
    msg = (f'Documentation: README, REPRODUCE, SOURCES, LICENSE, corpus.json, tools and data\n\n'
           f'Built from the legalinfo.mn cache retrieved on {retrieved}. No law text changes.\n\n'
           f'In-force: {retrieved}\nKind: documentation\n')
    last = commit('refs/heads/main', None, docs, ('Lexifina', 'mongolia-law@lexifina.com'), retrieved, msg, last)
    tip = last
    for c in future:
        tip = commit('refs/heads/future', c, c['files'], c['author'], c['day'], message(c), tip)
    if not future:
        w(f'reset refs/heads/future\nfrom :{last}\n\n'.encode())
    w(b'done\n')
    proc.stdin.close()
    if proc.wait():
        sys.exit('git fast-import failed')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', type=Path)
    ap.add_argument('--today', required=True)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--workers', type=int, default=6)
    args = ap.parse_args()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.today):
        sys.exit('--today must be YYYY-MM-DD')
    retrieved = (CACHE / 'fetched_on.txt').read_text('utf-8').strip()
    if retrieved > args.today:
        sys.exit(f'retrieval date {retrieved} is after --today {args.today}')
    laws = load_laws(args.limit)
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(args.workers) as pool:
        built = list(pool.map(build_law, laws, chunksize=4))
    main_c, future_c, issues = plan(laws, built, retrieved, args.today)
    notes = [r for b in built for r in b['notes']]
    print(f'{len(laws)} laws, {len(main_c)} main commits, {len(future_c)} future commits, {len(issues)} issues, '
          f'{len(notes)} notes', flush=True)

    import docs as docmod
    docs = docmod.render(laws, built, main_c, future_c, issues, notes, args.today, retrieved)

    repo = args.repo
    remote = None
    if repo.exists() and any(repo.iterdir()):
        if not (repo / '.git').exists():
            sys.exit(f'{repo} is not empty and not a git repository; refusing')
        r = subprocess.run(['git', '-C', str(repo), 'log', '--all', '--format=%ae'], capture_output=True, text=True)
        authors = set(r.stdout.split())
        bad = {a for a in authors if not (a.endswith('legalinfo-mn.invalid') or a in (
            'mongolia-law@lexifina.com', 'world-law@lexifina.com'))}
        if bad:
            sys.exit(f'{repo} holds commits by {sorted(bad)}; refusing to replace it')
        remote = subprocess.run(['git', '-C', str(repo), 'remote', 'get-url', 'origin'], capture_output=True,
                                text=True).stdout.strip() or None
        import os
        import shutil
        import stat

        def onerr(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        for child in repo.iterdir():
            shutil.rmtree(child, onerror=onerr) if child.is_dir() else child.unlink()
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
    for k, v in (('core.autocrlf', 'false'), ('core.longpaths', 'true'), ('core.quotepath', 'false')):
        subprocess.run(['git', '-C', str(repo), 'config', k, v], check=True)
    if remote:
        subprocess.run(['git', '-C', str(repo), 'remote', 'add', 'origin', remote], check=True)
    fast_import(repo, main_c, future_c, docs, retrieved)
    subprocess.run(['git', '-C', str(repo), 'checkout', '-q', '-f', 'main'], check=True)
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    count = subprocess.run(['git', '-C', str(repo), 'rev-list', '--count', 'HEAD'], capture_output=True,
                           text=True).stdout.strip()
    print(f'built {repo}: {count} commits on main, head {head}', flush=True)


if __name__ == '__main__':
    main()
