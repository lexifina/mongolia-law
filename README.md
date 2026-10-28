# Mongolia: the Constitution and the laws in force, as git

The Constitution of Mongolia and the 951 laws of Mongolia (Монгол Улсын хууль) that the Unified Legal
Information System, [legalinfo.mn](https://legalinfo.mn), lists as in force, in Mongolian (Cyrillic), as published there
on 2026-10-28. One folder per law, one file per article, one paragraph per line.

**This is a current-only record.** legalinfo.mn publishes each law's current consolidated text and the list of acts that
amended it, and for 30 laws also the original text, but no dated versions in between. So you can read the law
as it stands, and for those laws as first adopted, but not the wording on a date in between.

## Questions, as git commands

| Question | Command |
|---|---|
| What does article 21 of the Constitution say now? | `git show main:undsen-khuuli/zuil-21.md` |
| What did it say as adopted in 1992? | `python tools/in_force_on.py 1992-03-01 undsen-khuuli zuil-21` |
| The whole Anti-Corruption Law on a date | `python tools/in_force_on.py 2026-10-28 huuli/8928` |
| Which acts amended a law, and when were they adopted? | `git log -1 --format=%B main -- huuli/8928` (the `Amended-by:` lines) |
| What changed between the original and the current text? | `git log -p --word-diff main -- undsen-khuuli/zuil-21.md` |
| Which provisions did an act of a given date change? | `grep 2019-11-14 data/amendments.csv` |
| Who wrote this line? | `git blame main -- undsen-khuuli/zuil-6.md` (a law for original text, the publisher for current text) |
| Which law is folder `huuli/8928`? | `grep huuli/8928, laws.csv` |
| What is not yet in force? | `git log main..future` |

Citations of an article ("4 дүгээр зүйл", "12 дугаар зүйл") can be found with
`git grep -E "(^|[^0-9.])4 ?(дүгээр|дугаар) зүйл"`; corpus.json carries the same rule for global-law.

In PowerShell, `git show "main:undsen-khuuli/zuil-21.md"`. For dates, use `tools/in_force_on.py`, which reads the
`In-force:` trailers; `git rev-list --before` reads commit times, which are noon in Ulaanbaatar.

## Dates

- **Original text** (where the site has it, or where it lists no amending act, so the current text is the text as
  adopted): dated by the law's own in-force date, "дагаж мөрдөх огноо" on legalinfo.mn (544 commits
  on main). The Constitution: in force from noon on 12 February 1992 (its Art. 70.2).
- **Current text**: dated by the retrieval day, 2026-10-28, the day the text was read as in force
  (435 commits). `Consolidated:` repeats that day; `Amended-by:` gives each amending act's
  adoption date, title and site id; `Unknown-from:` gives the first amending act's adoption date, from which the earlier
  commit's text may no longer be the law. An amended law whose page has no original text ("Анхны эх") has this commit
  only, with `Original-text: not published on legalinfo.mn` (408 laws).
- Every commit carries `In-force: YYYY-MM-DD`. Commit times are 12:00 Asia/Ulaanbaatar (UTC+8, UTC+9 in summer time
  1983-1998, 2001-2006 and 2015-2016). Dates before 1970 are clamped to 1970-01-01 in git; the trailer keeps the real day.
- 189 laws have no in-force date on the site: their original text is dated by the adoption date, with
  `Evidence: no in-force date given; adoption date used`. 7 laws have an in-force date before their
  adoption date (they reach back); the commit keeps the in-force date and `Adopted:` gives the adoption date.
- Laws whose in-force date is after 2026-10-28 are on the `future` branch (0 commits), which is never merged.

## How it is checked

check_repo.py: 952 laws and 979 versions read back from git and compared word for word with the site's HTML: 0 mismatches; 980 commits, 0 with unparseable trailers; tool samples 6/6 right. check_letters.py, which shares no code with build.py, compared the letters and digits of every version with the raw page: 979 versions, 0 mismatches.
Rebuild: two builds from the same cache on 2026-10-28 gave the same law history, tip 2f43cabea64a800066310aa114f882af8bb4e3a5 (the commit before the documentation commit), and the same main hash when run with the same check results
`scripts/global-law/check_corpus.py` passes.

## What "author" means

- A commit with the original text is authored by the law: its title and adoption date, `law-<id>@legalinfo-mn.invalid`.
- A commit with the current text is authored by the publisher, "Эрх зүйн мэдээллийн нэгдсэн систем (legalinfo.mn)":
  its words come from several amending acts, and the site does not say which act wrote which words at which date
  beyond its per-provision notes. Blame on those lines names the publisher, not a law.
- The committer is always `Lexifina <mongolia-law@lexifina.com>`.

## What it does not show

- **The wording between the original and the current text.** Not published; no replay of amending acts was attempted.
- **Text not yet applicable inside the current text.** The publisher's notes such as "/Энэ хэсгийг 2028 оны 01 дүгээр
  сарын 01-ний өдрөөс эхлэн дагаж мөрдөнө./" (applies from 1 January 2028) stay in the text; 1
  distinct future dates appear in such notes. They are listed in data/amendments.csv (kind `applies-from`).
- **Annexes** (the "Хавсралт" tab, 30 laws) are not included; tables inside the text are kept, one row
  per line with cells joined by " | ".
- **Repealed laws**, international treaties, resolutions of the State Great Khural, decrees and regulations.
- **Translations.** The English texts on the site are not official and are not included.
- **Article numbering.** Inserted articles keep the site's superscript: "Арван ес¹ дүгээр зүйл" is `zuil-19-1.md`;
  codes numbered by chapter ("1.1 дүгээр зүйл") are `zuil-1.1.md`. A number used twice in one law gets `~2`.

## How it is built

`scripts/mongolia-law/fetch.py` reads the site's list of laws in force and each law's page and amendment list;
`build.py` splits the texts into articles and writes the history with one `git fast-import` stream; the same cache
always gives the same hashes. See REPRODUCE.md. No AI model wrote or changed any legal text, and none runs at build time.

## Licence and source

The texts are Mongolian legislation, which is not protected by copyright. Law of Mongolia on Copyright (revised),
6 May 2021, Article 7, as published on legalinfo.mn (https://legalinfo.mn/mn/detail?lawId=16230812154721):

> 7 дугаар зүйл.Зохиогчийн эрхээр үл хамгаалах зүйл
> 7.1.Дараах зүйлийг зохиогчийн эрхээр хамгаалахгүй:
> 7.1.1.хууль тогтоомж, захиргааны хэм хэмжээний акт, эрх зүйн бусад акт;
> 7.1.2.төрийн захиргааны байгууллага, хуулийн этгээдийн шийдвэр, албан бичиг;

("The following are not protected by copyright: laws, administrative normative acts and other legal acts.")

Source: Эрх зүйн мэдээллийн нэгдсэн систем, legalinfo.mn (Хууль зүйн үндэсний хүрээлэн, National Legal Institute of
Mongolia). The site's footer reads "© 2025 legalinfo.mn Бүх эрх хуулиар хамгаалагдсан"; the structure, file layout,
commit history and tools here are Lexifina's and are CC0. This repository is private.
