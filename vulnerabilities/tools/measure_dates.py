"""Counts the Mongolian "until" dates in the law texts at a commit and how many of them the time-limit search reads.

    python -X utf8 measure_dates.py <scripts dir> <commit>

A date is "2020 оны 12 дугаар сарын 31-ний өдрийг хүртэл" (or "... өдөр хүртэл", "... дуустал"); a year alone
("2030 он хүртэл", "2000 он дуустал") is counted apart. The scripts dir holds sources/corpus/mongolia-law.git and ingest/.
"""
import re, subprocess, sys
S, PIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, S + "/ingest")
import textscan  # noqa: E402

G = S + "/sources/corpus/mongolia-law.git"
ls = subprocess.run(["git", "-C", G, "grep", "-l", "-E", "(хүртэл|дуустал)", PIN, "--", "law", "constitution"],
                    capture_output=True).stdout.decode("utf-8").split("\n")
DAY = re.compile(r"\d{4} оны \d{1,2} (?:дугаар|дүгээр) сарын \d{1,2}\S* ?(?:өдрийг |өдөр )?(?:хүртэл|дуустал)")
YEAR = re.compile(r"\d{4} он (?:хүртэл|дуустал)")
day = year = read = 0
for f in filter(None, ls):
    t = subprocess.run(["git", "-C", G, "show", f], capture_output=True).stdout.decode("utf-8")
    day += len(DAY.findall(t))
    year += len(YEAR.findall(t))
    read += sum(1 for _ in textscan.limits(t))
print(f"until a day: {day}; until a year: {year}; read by the time-limit search: {read}")
