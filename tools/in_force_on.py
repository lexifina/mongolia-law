"""Print a Mongolian law, or one article of it, as this repository has it on a date, with the warnings that matter.

    python tools/in_force_on.py 2026-10-28 undsen-khuuli               # the whole Constitution
    python tools/in_force_on.py 2000-01-01 undsen-khuuli zuil-21       # Constitution, art. 21, as recorded then
    python tools/in_force_on.py 2026-10-28 huuli/8928 zuil-4           # Anti-Corruption Law, art. 4

Reads the `In-force:` trailers (the real dates; commit dates before 1970 would be clamped) of `main`, first-parent
only (the `future` branch is never read). legalinfo.mn keeps only a law's original text (for a few laws) and its
current text, so:
  - a date on or after the retrieval day gives the current text;
  - an earlier date gives the original text if there is one, with a warning when an amending act was adopted on or
    before that date (the trailer `Unknown-from:`): the wording in force then is not published;
  - otherwise there is no version for that date.
Standard library only.
"""
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', check=True).stdout


def history(path: str) -> list[tuple[str, str, str, str]]:
    """(hash, in-force, kind, unknown-from) for every main commit touching path, newest first."""
    fmt = ('%H%x1f%(trailers:key=In-force,valueonly,separator=)%x1f%(trailers:key=Kind,valueonly,separator=)'
           '%x1f%(trailers:key=Unknown-from,valueonly,separator=)')
    out = []
    for line in git('log', '--first-parent', f'--format={fmt}', 'main', '--', path).splitlines():
        h, d, kind, unknown = (line.split('\x1f') + ['', '', ''])[:4]
        if d.strip():
            out.append((h, d.strip(), kind.strip(), unknown.strip()))
    return out


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    day, law = sys.argv[1], sys.argv[2].strip('/')
    unit = sys.argv[3] if len(sys.argv) > 3 else None
    if unit and unit.endswith('.md'):
        unit = unit[:-3]
    path = f'{law}/{unit}.md' if unit else law
    hist = history(law)
    if not hist:
        sys.exit(f'{law}: not found')
    pick = next((c for c in hist if c[1] <= day), None)
    if pick is None:
        sys.exit(f'{law}: no version on or before {day}; the record starts at {hist[-1][1]}')
    later = [c for c in hist if c[1] > day and c[3]]
    for h, d, kind, unknown in later:
        if unknown <= day:
            sys.stderr.write(f'warning: {law} was amended by an act adopted {unknown}, on or before {day}; legalinfo.mn '
                             f'does not publish the wording in force on {day}. Shown: the {pick[2] or "recorded"} text '
                             f'in force from {pick[1]}; the current text is recorded from {d}.\n')
    if unit:
        try:
            sys.stdout.write(git('show', f'{pick[0]}:{path}'))
        except subprocess.CalledProcessError:
            sys.exit(f'{path}: no such article in the version in force from {pick[1]}')
        return
    try:
        names = [n for n in git('show', f'{pick[0]}:{law}/index.txt').splitlines() if n]
    except subprocess.CalledProcessError:
        names = sorted(n.rsplit('/', 1)[-1] for n in git('ls-tree', '--name-only', pick[0], f'{law}/').split())
    for n in names:
        sys.stdout.write(git('show', f'{pick[0]}:{law}/{n}') + '\n')


if __name__ == '__main__':
    main()
