# Tools

The scripts behind this Mongolia-only run of global-law's vulnerability detectors. They run inside a copy of
[global-law/vulnerabilities/scripts](https://github.com/lexifina/global-law/tree/main/vulnerabilities/scripts) (Python 3.11+,
`pip install duckdb pyarrow`), with a bare clone of this repository at `sources/corpus/mongolia-law.git`, a blobless bare
clone of global-law at `sources/global-law.git`, and a `pins.json` that names only mongolia-law and its commit (language
`mn`). `build_vulns.py`, `flags_chart.py`, `late_ext_select.py` and `late_ext_rebut.py` sit two folders above the scripts,
next to `config.json`.

| Script | What it does |
| --- | --- |
| `run.sh` | Indexes the history and texts, maps paths to the folders since the move (`map_moved.py`), adds this repository's history rows, and runs the detectors (`bash run.sh <shards>`) |
| `add_root.py` | Builds the history rows from this repository's own commits (global-law replays it only up to an earlier commit), so the history detectors read every change |
| `map_moved.py` | Rewrites the paths in the history table to each act's folder since the move of 10 November 2026 (`data/paths.json`: `huuli/16230709635751/` to `law/2021/16230709635751/`), so that an act's history is not split in two at the move; `run.sh` runs it after the history is indexed |
| `patch_mn.py` | The Mongolian fixes below, in the copy of global-law's scripts (`python -X utf8 patch_mn.py <scripts dir>`; a fix already in place is skipped) |
| `run_triage.sh` | The model review: the 40 strongest flags per category, the 40 strongest lapsed time limits in law texts, and the empty periods |
| `late_ext_select.py` | Chooses the empty periods for global-law's review of that category (there were none here) |
| `late_ext_rebut.py` | Adds the second, arguing-against pass to the empty-period review, as `triage.py` does for the other categories |
| `build_vulns.py` | Builds `data/flags.csv`, `data/reviewed.csv` and `data/by_category.csv` from the findings and the model review |
| `flags_chart.py` | Draws the chart at the top of the READMEs, in Mongolian and English, light and dark |
| `config.json` | The repository, the Mongolian category names, the files that are not law, and the chart's labels |
| `patch_detectors.py` | Fixes blind spots found in runs on several country repositories in the copy of global-law's scripts (`python -X utf8 patch_detectors.py <scripts dir>`; a fix already in place is skipped) |
| `patch_detectors_vi.py`, `patch_es.py`, `patch_ca.py`, `patch_en.py`, `patch_de.py`, `patch_en_et.py`, `patch_co.py`, `patch_sv.py`, `patch_pt.py`, `patch_ru.py`, `patch_r18.py`, `patch_xk.py`, `patch_mo.py`, `patch_lu.py`, `patch_li.py` | The same for the Vietnamese, Spanish, Catalan, English (two rounds), German, Colombian, Salvadoran, Brazilian Portuguese, Russian, Kosovo, Macau, Luxembourg and Liechtenstein blind spots found by other runs, and an eighteenth round found by the Germany run (`patch_r18.py`); this run's copy carries them all. `patch_ru.py` is for Russian (it reads "не позднее", "статья" and the `statya-012.md` files) and changes nothing here: Mongolian is written in Cyrillic too, but it is a different language |
| `apply_patches.py` | Applies every patch above once, in order, and records each in the scripts folder (`python -X utf8 apply_patches.py <scripts dir>`); `patch_mn.py` is last |
| `redo.py` | Runs those patches through `apply_patches.py`, then again only the scans and detectors the fixes change, the model review of lapsed time limits, references to deleted provisions and empty periods, and the build (`python -X utf8 redo.py <run folder> [--keep-reviews] [--full]`; `--keep-reviews` keeps every review already made and reviews only new strong flags; `--full` runs every step again through `run.sh`; `EMBED_FONTS` names the script that embeds the chart's fonts) |
| `measure_dates.py` | Counts the places in the law texts where "хүртэл" or "дуустал" follows a date, and how many of them the time-limit search reads (the numbers in the READMEs: `python -X utf8 measure_dates.py <scripts dir> <commit>`) |

The model review needs `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` and `LLM_AUTH` set for an OpenAI-compatible Responses API.
It was run as `bash run_triage.sh '^(data|tools|vulnerabilities)/|^(README|REPRODUCE|SOURCES|LICENSE|corpus[.]json|laws[.]csv)'`;
every law is under `constitution/` or `law/`, so the review of lapsed time limits in law texts drew almost the same flags as
the review of all of them, and `build_vulns.py` keeps the later review of each flag.

Changes made for this repository:

- `add_root.py`: the kit already counted `Kind: original` (the 544 texts as adopted) as law. The 435 current texts
  (`Kind: consolidated`) are left out: legalinfo.mn publishes no dated versions in between, so each of them is credited to
  the publisher and dated by the day it was read (28 October 2026), not by the day of any change; the 2 documentation commits
  are left out too.
- `add_root.py`: each commit names its law in a `Law:` trailer that holds the bare title, which several acts share (four
  of the flagged acts are called "ГААЛИЙН АЛБАН ТАТВАРААС ЧӨЛӨӨЛӨХ ТУХАЙ" or "НЭМЭГДСЭН ӨРТГИЙН АЛБАН ТАТВАРААС ЧӨЛӨӨЛӨХ ТУХАЙ"),
  while the commit's author adds the day of adoption ("... (2016-02-04)"). The detectors group by law, so acts of the same
  name were read as one: the first run found 4 retroactive dates, each mixing the dates of several acts. An author that is
  the `Law:` title followed by " (" is now used instead: 7 retroactive dates, one per act, as in global-law's own list.
- `patch_mn.py`, time limits: Mongolian writes the year first, the month as an ordinal and "until" after the date ("2020
  оны 12 дугаар сарын 31-ний өдрийг хүртэл", "... 31-ний өдөр хүртэлх хугацаанд", "... 31-ний өдрийг дуустал"), which the
  search did not read: it found none of the 191 such dates in the law texts. It now reads all 191, and "2000 он дуусталх"
  (until the year 2000 ends, 2 places); 5 places with a year alone and "хүртэл" ("2030 он хүртэл") are left out, as they do
  not say whether the year itself is included. Lapsed time limits went from 1 (in the English README) to 132.
- `patch_mn.py`, references: the article files here are `zuil-21.md` and, for an inserted article, `zuil-19-1.md` (article
  19¹), which had no key, so the reference-based detectors saw no article at all; "энэ хуулийн 7 дугаар зүйл" (article 7 of
  this law) was not read as a reference (only "хуулийн 7.1-д" was); and a reference to another law ("Эрүүгийн хуулийн
  131.1-д", "Банкны тухай хуулийн 3 дугаар зүйл") was read as one to the act's own article. Only "энэ хуулийн", "энэ
  журмын" and "энэ дүрмийн" (this law, these rules) now count as the act's own. Articles numbered by chapter, as in the
  Criminal Code of 2015 ("1.10 дугаар зүйл", `zuil-1.10.md`, 1,058 files), still have no key.
- `patch_mn.py`, references to repealed placeholders: a repealed article's file reads "59 дүгээр зүйл./Энэ зүйлийг 1995
  оны 12 дугаар сарын 11-ний өдрийн хуулиар хүчингүй болсонд тооцсон/."; "хүчингүй болсонд тооцсон" (deemed repealed) is
  now a repeal marker, and the article's label at the start of the same line no longer pushes the marker past the 70
  characters it may start in. This category went from 0 flags to 1.
- `config.json` counts the top-level files (`README.md`, `README.en.md`, `REPRODUCE.md`, `SOURCES.md`, `LICENSE`,
  `corpus.json`, `laws.csv`), `data/` and `tools/` as not law; each act's `index.txt` (its list of files) has no date or
  reference in it, and its `ehlel.md` (the text before the first article) is part of the act.
- `pins.json` already named the language (`mn`). `build_vulns.py` reported "56 of 60 reviews matched": the 4 that did not
  match are the reviews of the first run's 4 mixed retroactive dates, made before the `add_root.py` fix; the model then
  reviewed the 7 flags that replaced them.
