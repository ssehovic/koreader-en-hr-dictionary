# English-Croatian dictionary for KOReader (Kindle)

This project converts a Kindle/MOBI dictionary (`English-Croatian.mobi`) into the
**StarDict** format so that [KOReader](https://koreader.rocks/) can use it for
offline word lookup on a Kindle (and on any other device running KOReader).

The conversion is done by two dependency-free Python 3 scripts that implement
just enough of the MOBI/PalmDOC and StarDict file formats to do the job.

## Deliverable

The ready-to-use dictionary lives in
**`English-Croatian-stardict/English-Croatian/`**:

| File | Size | Description |
|---|---|---|
| `English-Croatian.ifo` | ~363 B | Metadata (`bookname`, `wordcount`, `synwordcount`, ...) |
| `English-Croatian.idx` | ~2.9 MB | Headword index (147,235 words) |
| `English-Croatian.idx.gz` | ~1.4 MB | Same index, gzip-compressed (sdcv prefers this one) |
| `English-Croatian.dict` | ~29 MB | Definitions (HTML, UTF-8) |
| `English-Croatian.syn` | ~1.2 KB | Synonyms / variant forms (73 entries, 49 unique words) |

For easy transfer there is also **`English-Croatian-stardict.zip`** (~11.5 MB).

## Installing on a Kindle (KOReader)

1. Connect the Kindle to a computer over USB.
2. Open KOReader's data folder. On Kindle it is:

   ```
   koreader/data/dict/
   ```

3. Copy the whole `English-Croatian` folder into `koreader/data/dict/`, so you
   end up with:

   ```
   koreader/data/dict/English-Croatian/English-Croatian.ifo
   koreader/data/dict/English-Croatian/English-Croatian.idx
   koreader/data/dict/English-Croatian/English-Croatian.idx.gz
   koreader/data/dict/English-Croatian/English-Croatian.dict
   koreader/data/dict/English-Croatian/English-Croatian.syn
   ```

   If you downloaded the `.zip`, unzip it first: KOReader looks for unpacked
   `.ifo` files, it does not read dictionaries from an archive.

4. Eject the Kindle safely and (re)start KOReader so it rescans the `dict`
   folder.
5. In a book, long-press a word to open the dictionary popup. If the dictionary
   does not appear, pick it under **Settings → Dictionary**, or long-press a
   dictionary name in the popup to reorder/enable it.

KOReader scans `data/dict` recursively, so the `English-Croatian/` sub-folder is
not strictly required, but it keeps things tidy.

## What mattered for this conversion

Converting this particular file required a few non-obvious details. They are the
reason a generic "MOBI → StarDict" tool did not work out of the box.

1. **MOBI is not readable by PyGlossary.** PyGlossary only ships a MOBI *writer*
   (it shells out to `kindlegen`); it cannot read MOBI. Calibre's
   `ebook-convert` can read it, but converting a 25 MB dictionary with 147k
   entries is slow. So the MOBI container and its PalmDOC compression are parsed
   directly in `extract_mobi.py`.

2. **PalmDOC "trailing entries" must be discarded.** Text records use PalmDOC
   compression (compression type 2). Each record decompresses to **more than
   4096 bytes**: the real text is at most 4096 bytes, and the extra bytes are
   per-record *trailing entries* (uncompressed metadata appended after the
   compressed stream). If they are not dropped, the decompressor keeps decoding
   them as if they were compressed data and injects binary garbage in the middle
   of the text (e.g. `<b>6-membered<\x00\x10 co.../b>`). Truncating every
   decompressed record to 4096 bytes fixes it.

3. **The text encoding field is at MOBI-header offset 0x0C, not 0x08.** Offset
   0x08 is the *Mobi type*. Reading the wrong offset made the parser think the
   text was `cp1252` when it is actually **UTF-8** (`65001`), which produced
   mojibake such as `kapulja�?a` instead of `kapuljača`.

4. **The PalmDB record table's final entry has a bogus offset.** The last of the
   `nrec + 1` entries is not a real record; its offset can be arbitrary (here it
   was `2`). Record sizes must therefore be clamped to the file size.

5. **The StarDict index must be sorted with `stardict_strcmp`.** That is
   `g_ascii_strcasecmp` followed by `strcmp` (ASCII-only case folding, then an
   exact byte comparison). sdcv performs a binary search over this order, so any
   other sort order breaks lookups.

6. **Entry bodies are HTML.** The dictionary content is marked with
   `sametypesequence=h`, which KOReader/sdcv render as HTML (bold translation
   line plus one or more `<p>` definition paragraphs).

7. **KOReader's dictionary engine is sdcv.** It supports `.idx`/`.idx.gz`,
   `.dict`/`.dict.dz` and an optional `.syn`, and it scans recursively for
   `*.ifo` under `data/dict`. If a `.idx.gz` exists it is preferred over `.idx`,
   and `idxfilesize` must then hold the *uncompressed* size.

8. **The `.syn` file should stay small.** It maps a synonym to the *ordinal
   index* of the headword in `.idx` (`word\0` + 4-byte big-endian index), and
   `synwordcount` in the `.ifo` must match exactly. In this dictionary 110,353
   of the 110,402 unique WordNet synonyms are already headwords, so only the
   49 that are not (e.g. `tuna fish` → `tuna`, `epaulet` → `epaulette`) are
   written to `.syn`. Adding all 305,084 synonym pairs would only create noise
   and slow lookups (e.g. looking up `house` would return 16 hits instead of
   one).

## Repository layout

```
English-Croatian.mobi              # source dictionary (input)
extract_mobi.py                    # MOBI/PalmDOC -> raw HTML
mobi2stardict.py                   # HTML -> StarDict (.ifo/.idx/.dict/.syn)
English-Croatian-stardict/         # generated StarDict dictionary
English-Croatian-stardict.zip      # the same dictionary, zipped for transfer
README.md
AGENTS.md
```

## The scripts

Both scripts use only the Python 3 standard library (no `pip install` needed).

### `extract_mobi.py` — MOBI/PalmDOC extractor

`python3 extract_mobi.py <input.mobi> <output.html>`

1. `load_records()` reads the PalmDB header, the record-offset table, and slices
   the file into records, clamping the last record's size to the file size.
2. `palmdoc_decompress()` implements the PalmDOC compression scheme (literal
   runs, literal bytes, space+`0x80` pairs, and length/distance back-references).
3. `main()` reads the MOBI header (compression type, text encoding, and the
   `first non-book` record index that separates text from index records), walks
   the text records, decompresses each one and **truncates it to 4096 bytes** to
   drop the trailing entries, then writes the concatenated HTML as UTF-8 (or
   cp1252 if the header says so). It also writes a `<output>.decoded.txt`
   convenience copy.

### `mobi2stardict.py` — StarDict builder

`python3 mobi2stardict.py <clean.html> <outdir> [basename]`

1. Splits the HTML on `<hr/>` into entry blocks. Each block starts with
   `<b>HEADWORD</b><br>`; the headword is unescaped and whitespace-normalised.
2. Cleans the article body (drops `<font>`/`<mbp:...>` tags, normalises `<br>`
   to `<br/>`) and keeps it as HTML.
3. Extracts synonyms from the `<font ...>[syn1, syn2, ...]</font>` lists.
4. Sorts entries with the StarDict collation, then writes:
   - `.dict` — concatenated article bytes;
   - `.idx` and `.idx.gz` — `word\0` + big-endian `offset` and `size`;
   - `.syn` — `synonym\0` + big-endian headword index, keeping only synonyms
     that are **not** themselves headwords;
   - `.ifo` — metadata, with `wordcount`, `synwordcount`, `idxfilesize` and
     `synfilesize` set to the exact byte counts.

## Regenerating the dictionary

```sh
mkdir -p work
python3 extract_mobi.py English-Croatian.mobi work/clean.html
python3 mobi2stardict.py work/clean.html stardict English-Croatian
```

The result is written to `stardict/`; copy it over `English-Croatian-stardict/`
and re-zip if you want to repackage.

## Source and licensing

The source `.mobi` (`English-Croatian Dictionary`) was generated from:

- WordNet 3.0 Easy, CroWN (Open Multilingual WordNet)
- FreeDict
- EH
- Wiktionary

Source licences: CC BY 3.0 (WordNet / CroWN / OMW), GPL (FreeDict / EH),
CC BY-SA (Wiktionary).
