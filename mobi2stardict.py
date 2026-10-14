#!/usr/bin/env python3
"""Convert the extracted MOBI dictionary HTML into StarDict
(.ifo/.idx/.dict/.syn).

The source HTML has one entry per "<hr/>"-separated block:

    <b>HEADWORD</b><br> <br/>
    <p><b>CROATIAN TRANSLATIONS ...</b></p>
    <p><i>pos.</i> ENGLISH DEFINITION <font ...>[synonyms]</font></p>
    ...

The bracketed words in the definition (the WordNet synset lemmas) are written
to the .syn file, so a lookup on an English synonym/variant also finds the
entry whose headword is the canonical form.
"""
from __future__ import annotations

import gzip
import html
import re
import struct
import sys
from pathlib import Path

HEAD_RE = re.compile(r"<b>(.*?)</b><br>")
FONT_RE = re.compile(r"</?font[^>]*>", re.IGNORECASE)
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
JUNK_RE = re.compile(r"<mbp:[^>]*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
# synonym lists appear as: <font ...>[syn1, syn2, ...]</font>
SYN_RE = re.compile(r"<font[^>]*>\s*\[([^\]]*)\]\s*</font>", re.IGNORECASE)


def extract_synonyms(body: str):
    syns = []
    for m in SYN_RE.finditer(body):
        for part in m.group(1).split(","):
            s = html.unescape(TAG_RE.sub("", part)).strip()
            s = WS_RE.sub(" ", s)
            if s:
                syns.append(s)
    return syns


def ascii_lower(s: str) -> str:
    """Lowercase ASCII only, like glib's g_ascii_strcasecmp used by StarDict."""
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def clean_article(body: str) -> str:
    body = JUNK_RE.sub("", body)
    body = FONT_RE.sub("", body)
    body = BR_RE.sub("<br/>", body)
    # strip whitespace between tags that only adds noise
    body = re.sub(r">\s+<", "><", body)
    body = body.strip()
    # drop a leading empty line
    body = re.sub(r"^(<br/>\s*)+", "", body)
    return body.strip()


def parse_entries(data: str):
    data = data.split("</html>", 1)[0]
    for block in data.split("<hr/>"):
        m = HEAD_RE.search(block)
        if not m:
            continue
        word = html.unescape(TAG_RE.sub("", m.group(1))).strip()
        word = WS_RE.sub(" ", word)
        if not word:
            continue
        body = block[m.end():]
        article = clean_article(body)
        if not article:
            continue
        yield word, article, extract_synonyms(body)


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "work/clean.html")
    outdir = Path(sys.argv[2] if len(sys.argv) > 2 else "stardict")
    basename = sys.argv[3] if len(sys.argv) > 3 else "English-Croatian"
    outdir.mkdir(parents=True, exist_ok=True)

    text = src.read_text(encoding="utf-8", errors="replace")
    entries = list(parse_entries(text))
    print(f"parsed entries: {len(entries)}")

    # sort using StarDict's ordering (ASCII-case-insensitive, then exact)
    entries.sort(key=lambda e: (ascii_lower(e[0]).encode("utf-8"),
                                e[0].encode("utf-8")))

    idx = bytearray()
    dic = bytearray()
    for i, (word, article, _syns) in enumerate(entries):
        wb = word.encode("utf-8")
        ab = article.encode("utf-8")
        offset = len(dic)
        dic += ab
        idx += wb + b"\x00" + struct.pack(">II", offset, len(ab))

    # Build the synonym table. Each synonym points to the *ordinal index* of
    # its headword in the .idx file. Synonyms that are themselves a headword
    # are skipped: sdcv finds those directly in the index, and keeping them
    # would only add noise (a common word appears in many synsets).
    headword_keys = {ascii_lower(w) for w in (e[0] for e in entries)}
    syn_seen = set()
    syn_pairs = []  # (synonym, headword_index)
    for i, (word, _article, syns) in enumerate(entries):
        wl = ascii_lower(word)
        for s in syns:
            sl = ascii_lower(s)
            if sl == wl or sl in headword_keys:
                continue
            key = (s, i)
            if key in syn_seen:
                continue
            syn_seen.add(key)
            syn_pairs.append((s, i))
    syn_pairs.sort(key=lambda si: (ascii_lower(si[0]).encode("utf-8"),
                                   si[0].encode("utf-8"), si[1]))

    syn = bytearray()
    for s, i in syn_pairs:
        syn += s.encode("utf-8") + b"\x00" + struct.pack(">I", i)
    syn_raw = bytes(syn)

    idx_raw = bytes(idx)
    idx_gz = gzip.compress(idx_raw, 9)

    ifo = "\n".join([
        "StarDict's dict ifo file",
        "version=2.4.2",
        f"wordcount={len(entries)}",
        f"synwordcount={len(syn_pairs)}",
        f"idxfilesize={len(idx_raw)}",
        f"synfilesize={len(syn_raw)}",
        f"bookname=English-Croatian Dictionary",
        "sametypesequence=h",
        "description=English to Croatian dictionary "
        "(WordNet 3 Easy, CroWN/OMW, FreeDict, EH, Wiktionary)",
        "author=Generated from WordNet 3 Easy, CroWN (OMW), FreeDict, EH, Wiktionary",
        "website=",
        "date=2026.10.14",
        "",
    ])

    (outdir / f"{basename}.ifo").write_text(ifo, encoding="utf-8")
    (outdir / f"{basename}.idx").write_bytes(idx_raw)
    (outdir / f"{basename}.idx.gz").write_bytes(idx_gz)
    (outdir / f"{basename}.dict").write_bytes(bytes(dic))
    (outdir / f"{basename}.syn").write_bytes(syn_raw)
    print(f"idx size: {len(idx_raw)} bytes (gz {len(idx_gz)})")
    print(f"dict size: {len(dic)} bytes")
    print(f"syn entries: {len(syn_pairs)} ({len(syn_raw)} bytes)")
    print(f"written to {outdir}/")


if __name__ == "__main__":
    main()
