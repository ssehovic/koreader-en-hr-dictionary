#!/usr/bin/env python3
"""Extract the raw HTML content out of a PalmDOC/MOBI e-book file."""
import struct
import sys


def load_records(path):
    with open(path, "rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(0)
        hdr = f.read(78)
        nrec = struct.unpack(">H", hdr[76:78])[0]
        ents = [struct.unpack(">LBBH", f.read(8)) for _ in range(nrec + 1)]
        recs = []
        for i in range(nrec):
            off = ents[i][0]
            end = ents[i + 1][0]
            if end <= off or end > file_size:  # last record uses a bogus offset
                end = file_size
            f.seek(off)
            recs.append(f.read(end - off))
    return hdr, recs


def palmdoc_decompress(data):
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        i += 1
        if 1 <= c <= 8:
            out += data[i:i + c]
            i += c
        elif c < 0x80:
            out.append(c)
        elif c >= 0xC0:
            out.append(0x20)
            out.append(c ^ 0x80)
        else:
            if i >= n:
                break
            c = (c << 8) | data[i]
            i += 1
            distance = (c >> 3) & 0x7FF
            length = (c & 0x07) + 3
            for _ in range(length):
                out.append(out[-distance])
    return bytes(out)


def main():
    path = sys.argv[1]
    outpath = sys.argv[2]
    hdr, recs = load_records(path)
    rec0 = recs[0]
    mobi_off = 16
    compression = struct.unpack(">H", rec0[0:2])[0]
    if rec0[mobi_off:mobi_off + 4] != b"MOBI":
        print("Not a MOBI file")
        return 1
    header_len = struct.unpack(">L", rec0[mobi_off + 4:mobi_off + 8])[0]
    encoding = struct.unpack(">L", rec0[mobi_off + 12:mobi_off + 16])[0]
    first_non_book = struct.unpack(">L", rec0[0x50:0x54])[0]
    text_records = first_non_book - 1
    print(f"compression={compression} encoding={encoding} "
          f"text_records={text_records} header_len={header_len}")

    text = bytearray()
    for r in recs[1:1 + text_records]:
        if compression == 1:
            text += r
        elif compression == 2:
            # Each MOBI text record decompresses to at most 4096 bytes of
            # text; any extra bytes are "trailing entries" and must be dropped.
            text += palmdoc_decompress(r)[:4096]
        else:
            raise SystemExit(f"unsupported compression {compression}")

    enc = "utf-8" if encoding == 65001 else "cp1252"
    data = bytes(text)
    with open(outpath, "wb") as f:
        f.write(data)
    # also write a decoded preview
    with open(outpath + ".decoded.txt", "w", encoding=enc, errors="replace") as f:
        f.write(data.decode(enc, errors="replace"))
    print(f"wrote {len(data)} bytes to {outpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
