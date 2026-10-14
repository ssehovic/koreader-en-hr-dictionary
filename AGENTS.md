# AGENTS.md

Guidance for AI coding agents working in this repository. Read this before
changing anything.

## What this project is

A one-shot data-conversion project: turn the Kindle/MOBI dictionary
`English-Croatian.mobi` into a **StarDict** dictionary that
[KOReader](https://koreader.rocks/) can use on a Kindle.

There is no build system and no runtime service. The "product" is a set of
binary dictionary files under `English-Croatian-stardict/`. The code is two
dependency-free Python 3 scripts.

Non-goals: no network access at runtime, no third-party Python packages.

## Repository layout

```
English-Croatian.mobi              # source dictionary (input, do not edit)
extract_mobi.py                    # MOBI/PalmDOC -> raw HTML
mobi2stardict.py                   # HTML -> StarDict (.ifo/.idx/.dict/.syn)
English-Croatian-stardict/         # generated output (the deliverable)
English-Croatian-stardict.zip      # same output, zipped for transfer
README.md                          # user-facing documentation
AGENTS.md                          # this file
work/                              # scratch output of extract_mobi.py (ignored)
stardict/                          # scratch output of mobi2stardict.py (ignored)
```

## Pipeline

```
English-Croatian.mobi
        │  python3 extract_mobi.py English-Croatian.mobi work/clean.html
        ▼
work/clean.html          (single-line HTML; one entry per <hr/> block)
        │  python3 mobi2stardict.py work/clean.html stardict English-Croatian
        ▼
stardict/English-Croatian.{ifo,idx,idx.gz,dict,syn}
```

Both scripts require **Python 3 standard library only**. Do not add pip
dependencies.

## Hard invariants — do not break these

These encode real, hard-won facts about the file formats. If a change touches
them, re-verify with the validation recipe below.

1. **Truncate every decompressed PalmDOC record to 4096 bytes.**
   Each MOBI text record decompresses to >4096 bytes because per-record
   *trailing entries* are appended *after* the compressed stream. Keeping them
   injects binary garbage into the text. See `extract_mobi.py`
   (`palmdoc_decompress(r)[:4096]`).

2. **The MOBI text encoding is at MOBI-header offset 0x0C, not 0x08.**
   0x08 is the Mobi type. Value `65001` = UTF-8, `1252` = cp1252. Reading the
   wrong offset causes mojibake. See `extract_mobi.py`.

3. **Clamp the last PalmDB record's size to the file size.**
   The extra entry in the record-offset table has a bogus offset. See
   `load_records()`.

4. **Sort both `.idx` and `.syn` with the StarDict collation.**
   That is `g_ascii_strcasecmp` (ASCII-only, case-insensitive) followed by
   `strcmp` (exact byte comparison). `ascii_lower()` implements the folding.
   sdcv binary-searches this order; any other order silently breaks lookups.

5. **`.syn` maps a synonym to the headword's ordinal index in `.idx`**, encoded
   as `synonym\0` + **4-byte big-endian** index. `synwordcount` in the `.ifo`
   must equal the exact number of `.syn` entries (sdcv uses it to compute
   offsets).

6. **`.ifo` sizes are exact byte counts of the *uncompressed* files.**
   `idxfilesize` is the size of `English-Croatian.idx`, not of the `.idx.gz`.
   sdcv prefers `.idx.gz` when it exists.

7. **Keep `.syn` filtered.** Only write a synonym when it is **not** already a
   headword (case-insensitive). This dictionary already contains 110,353 of the
   110,402 unique synonyms as headwords; storing all pairs adds noise and makes
   common lookups return many hits. If you intentionally want the full synset
   dump, that is a deliberate behaviour change — update `README.md` too.

8. **`sametypesequence=h`** because entry bodies are HTML. KOReader/sdcv render
   it.

## Validating changes

Always run an end-to-end regeneration and then the structural checks. There is
no test suite; use these ad-hoc checks (stdlib only).

```sh
mkdir -p work
python3 extract_mobi.py English-Croatian.mobi work/clean.html
python3 mobi2stardict.py work/clean.html stardict English-Croatian
```

Then verify (adapt paths):

- `.idx.gz` decompresses to exactly `.idx`; its length equals `idxfilesize`.
- `.dict` length is the sum of all `word_data_size` values; offsets are
  contiguous and in bounds; every slice decodes as UTF-8.
- `.idx` and `.syn` are sorted with the StarDict collation.
- `wordcount` / `synwordcount` equal the real entry counts.
- Every `.syn` index is a valid headword index, and no synonym is itself a
  headword.
- Spot-check entries decode correctly (Croatian letters `č ć ž š đ` render as
  UTF-8, not mojibake), e.g. look up `'tween`, `absolute`, `Zyrian`, `house`.

For an independent reader check, `pystardict` (pip) reads the `.ifo/.idx/.dict`
and is a good cross-implementation sanity test; it ignores `.syn`.

Cross-reference facts against the real sdcv source when in doubt:
`src/stardict_lib.cpp` in <https://github.com/Dushistov/sdcv> (`Dict::load`,
`SynFile::load`, `SynFile::lookup`, `Dict::Lookup`, `stardict_strcmp`). The
StarDict spec is in the `pysuxing/python-stardict` docs.

## Conventions

- English for code, comments, commit messages, and docs.
- Standard library only; keep scripts self-contained and importable-checked
  (`python3 -c "import ast; ast.parse(open('extract_mobi.py').read())"`).
- Keep functions small and named for the format concept they implement.
- When you change behaviour, update both `README.md` and this file.

## Definition of done

- `extract_mobi.py` + `mobi2stardict.py` run clean on the source `.mobi`.
- Output passes every check in "Validating changes".
- The refreshed files are copied into `English-Croatian-stardict/English-Croatian/`
  and `English-Croatian-stardict.zip` is rebuilt.
- `README.md` (and this file) reflect reality.

## Known extension points

Only pursue these if explicitly asked:

- Emit `.dict.dz` (dictzip) instead of plain `.dict` to shrink the payload.
- Full `.syn` (all WordNet synset members) — see invariant 7 for the trade-off.
- Inflection/stemming (e.g. `ran` → `run`). Not possible via `.syn` alone;
  KOReader handles morphology separately (hunspell), so this would be a
  different feature.
