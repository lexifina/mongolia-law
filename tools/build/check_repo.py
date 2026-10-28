"""Check the Mongolia law repository against the legalinfo.mn cache, independently of build.py's text parser.

    python -X utf8 scripts/mongolia-law/check_repo.py C:/Users/alany/Documents/mongolia-law

For every law and every commit that holds its text, the files (joined in index.txt order) must give exactly the words of
the site's HTML for that text (tags stripped with a regex, entities decoded, <sup> digits as superscripts, whitespace
split): 0 mismatches. Every commit must carry In-force: in its trailer block. tools/in_force_on.py is run on samples.
Writes .cache/verification.json, which docs.py quotes in README.md.
"""
import gzip
import html
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
sys.path.insert(0, str(HERE))
import build  # noqa: E402  (only for the page slicing of tab 1, and the law list)


def original_slice(page: str) -> str | None:
    """Tab 10 ("Анхны эх"), sliced here, not by build.py: from the end of its '--nomigration' opening tag to the
    start of the next element whose id is another tab (usually tab 11, the English translation) or the footer."""
    a = page.find('id="active-tab-10"')
    if a < 0:
        return None
    nxt = re.search(r'<[a-z]+[^>]* id="(?:active-tab-\d+|bordered-tab\d+)"|<div class="tw-fixed"', page[a + 18:])
    end = a + 18 + nxt.start() if nxt else len(page)
    m = re.search(r'--nomigration">', page[a:end])
    return page[a + m.end():end] if m else None


def git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8',
                          check=True).stdout


def words_of_html(fragment: str) -> list[str]:
    s = re.sub(r'(?is)<sup[^>]*>\s*([0-9]+)\s*</sup>', lambda m: m.group(1).translate(build.SUP), fragment)
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?s)<!--.*?-->|-->', ' ', s)  # comments, and the tail of one cut by the slice
    # a tag may hold '>' inside a quoted attribute (the site has <p style="padding-left: 3rem; >text-align:justify">);
    # block tags separate words, inline tags (a, span, b, sup ...) do not
    tag = r'<(/?)([a-zA-Z0-9]+)(?:[^>"\']|"[^"]*"|\'[^\']*\')*>'
    s = re.sub(tag, lambda m: ' ' if m.group(2).lower() in BLOCKS else '', s)
    s = html.unescape(s).replace(build.HEAD, ' ')
    s = build.DROP.sub('', s)
    return [w for w in s.split() if w != '|']


BLOCKS = {'p', 'div', 'br', 'td', 'th', 'tr', 'table', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
          'blockquote', 'center', 'section', 'article', 'dl', 'dt', 'dd', 'pre', 'address', 'tbody', 'thead', 'img',
          'hr'}


class Blobs:
    def __init__(self, repo: Path):
        self.p = subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE)

    def get(self, spec: str) -> bytes | None:
        self.p.stdin.write(spec.encode('utf-8') + b'\n')
        self.p.stdin.flush()
        head = self.p.stdout.readline().split()
        if len(head) < 3 or head[1] == b'missing':
            return None
        data = self.p.stdout.read(int(head[2]))
        self.p.stdout.read(1)
        return data


def main() -> None:
    repo = Path(sys.argv[1])
    blobs = Blobs(repo)
    laws = {l['folder']: l for l in build.load_laws(None)}
    fmt = '%H%x1f%(trailers:key=In-force,valueonly,separator=)%x1f%(trailers:key=Kind,valueonly,separator=)%x1f%B%x1e'
    records = [r.strip('\n').split('\x1f') for r in git(repo, 'log', '--first-parent', '--all', f'--format={fmt}')
               .split('\x1e') if r.strip()]
    commits = len(records)
    # the repository's placeholder root ("Mongolia: sources, before any law") holds no law and needs no In-force:
    bad_trailers = [r[0][:9] for r in records if not r[1].strip() and not r[3].startswith('Mongolia: sources, before any law')]
    checked = mismatches = versions = 0
    problems = []
    for h, inforce, kind, body in records:
        kind = kind.strip()
        if kind not in ('original', 'consolidated'):
            continue
        folder = re.search(r'^Law-id: (\d+)$', body, re.M).group(1)
        law = next(l for l in laws.values() if l['lawId'] == folder)
        page = gzip.decompress((CACHE / 'doc' / f"{law['lawId']}.html.gz").read_bytes()).decode('utf-8', 'replace')
        from_original = kind == 'original' and 'current text taken as adopted' not in body
        frag = original_slice(page) if from_original else build.current_fragment(page)
        want = words_of_html(frag)
        index = blobs.get(f"{h}:{law['folder']}/index.txt")
        if index is None:
            problems.append([law['folder'], h[:9], 'no index.txt'])
            mismatches += 1
            continue
        got = []
        for name in index.decode('utf-8').split():
            got += [w for w in blobs.get(f"{h}:{law['folder']}/{name}").decode('utf-8').split() if w != '|']
        versions += 1
        if got != want:
            mismatches += 1
            i = next((k for k, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
            problems.append([law['folder'], h[:9], f'word {i}: repo {got[i:i + 5]} site {want[i:i + 5]} '
                             f'({len(got)} vs {len(want)} words)'])
    checked = len({p for p in laws})

    # every page with an original text in Cyrillic must have an original commit (no translation swallowed, none lost)
    with_orig = {re.search(r'^Law-id: (\d+)$', b, re.M).group(1) for _, _, k, b in records
                 if k.strip() == 'original' and 'current text taken as adopted' not in b}
    for law in laws.values():
        page = gzip.decompress((CACHE / 'doc' / f"{law['lawId']}.html.gz").read_bytes()).decode('utf-8', 'replace')
        frag = original_slice(page)
        if frag is None:
            continue
        letters = re.findall('[A-Za-zЀ-ӿ]', ' '.join(words_of_html(frag)))
        if letters and sum(c < '' for c in letters) * 2 < len(letters) and law['lawId'] not in with_orig:
            problems.append([law['folder'], '-', 'site has an original text, repo has no original commit'])
            mismatches += 1

    # tool samples (run from the repo, as a reader would)
    samples = []
    tool = repo / 'tools' / 'in_force_on.py'
    retrieved = (CACHE / 'fetched_on.txt').read_text('utf-8').strip()
    def run(*a):
        return subprocess.run([sys.executable, '-X', 'utf8', str(tool), *a], cwd=repo, capture_output=True,
                              text=True, encoding='utf-8')
    head = git(repo, 'rev-parse', 'main').strip()
    for folder, unit in (('undsen-khuuli', 'zuil-21'), ('huuli/8928', 'zuil-4'), ('huuli/1', 'zuil-1')):
        r = run(retrieved, folder, unit)
        want = blobs.get(f'{head}:{folder}/{unit}.md')
        samples.append(r.returncode == 0 and want is not None and r.stdout.encode('utf-8') == want)
    orig = subprocess.run(['git', '-C', str(repo), 'log', '--first-parent', '--format=%H', '--grep', '^Kind: original',
                           'main', '--', 'undsen-khuuli'], capture_output=True, text=True).stdout.split()
    if orig:
        r = run('1992-03-01', 'undsen-khuuli', 'zuil-21')
        samples.append(r.stdout.encode('utf-8') == blobs.get(f'{orig[-1]}:undsen-khuuli/zuil-21.md') and not r.stderr)
        r = run('2010-01-01', 'undsen-khuuli', 'zuil-21')
        samples.append('warning' in r.stderr and r.stdout.encode('utf-8') == blobs.get(f'{orig[-1]}:undsen-khuuli/zuil-21.md'))
    r = run('1980-01-01', 'huuli/8928')
    samples.append(r.returncode != 0)
    out = {'laws': checked, 'versions': versions, 'mismatches': mismatches, 'commits': commits,
           'bad_trailers': len(bad_trailers), 'tool_samples': len(samples), 'tool_ok': sum(samples),
           'problems': problems[:200]}
    (CACHE / 'verification.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), 'utf-8')
    print(json.dumps({k: v for k, v in out.items() if k != 'problems'}), flush=True)
    for p in problems[:20]:
        print(p)
    if bad_trailers:
        print('commits without In-force:', bad_trailers[:10])
    print('tool samples:', samples)
    sys.exit(1 if mismatches or bad_trailers or not all(samples) else 0)


if __name__ == '__main__':
    main()
