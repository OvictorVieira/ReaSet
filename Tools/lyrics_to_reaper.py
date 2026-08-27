#!/usr/bin/env python3
"""Turn lyric sheets into REAPER track templates, one per song.

WHY A TRACK TEMPLATE AND NOT MIDI
---------------------------------
The Ableton version of this generator writes one MIDI file per line and puts
the line in the MIDI track name, because AbleSet reads the CLIP NAME and Live
has nowhere else to keep text.

That does not carry over. ReaSet reads **Item Notes** — `ULT_GetMediaItemNote`,
a different field from the take name — so importing MIDI files into REAPER
would produce items named after each line and a lyrics panel that stays empty.

A REAPER **track template** does carry it: it is an RPP chunk, and an `<ITEM>`
in an RPP chunk can hold a `<NOTES>` block. One file per song, dropped into the
project, gives you the whole track with every line already in place — then you
drag the edges to fit the music, which is the part only you can do.

USAGE
-----
    python3 Tools/lyrics_to_reaper.py lyrics_input/ -o reaper_output/

    python3 Tools/lyrics_to_reaper.py "lyrics_input/Numb.txt" --seconds 4

Input is one lyric line per text line, blank lines ignored — the same .txt the
Ableton generator consumes, so nothing has to be converted.

In REAPER: Track → Insert track from template, or drag the .RTrackTemplate onto
the track panel. The track arrives named `Lyrics`, which is the exact name the
bridge looks for.

If you are already inside REAPER, Tools/Lyrics_Tapper.lua does this without a
file at all: Load .txt, then Generate spreads the lines across the region.
This script exists for the batch — every song in a folder, in one command.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# Section headers a lyric sheet carries that are not sung. Deliberately a
# SMALL list of bare words: this runs unattended over a folder, and swallowing
# a real lyric line that happens to read like a header is worse than leaving a
# stray "Chorus" item for you to delete.
#
# One overlap is worth knowing before it surprises you: "outro" is an English
# section name AND the Portuguese word for "another", so a line that is exactly
# "outro" is dropped. Pass --keep-sections when that matters. The Lyrics
# Tapper's list has the same overlap, on purpose — two tools that disagree
# about what a header is would be worse.
SECTION_RE = re.compile(
    r"^[\[\(\{]?\s*"
    r"(chorus|pre[- ]?chorus|post[- ]?chorus|verse|bridge|intro|outro|ending"
    r"|hook|refrain|interlude|instrumental|solo|break|drop|tag|section|part"
    r"|coro|estribillo|verso|estrofa|puente|interludio|final"
    r"|refrão|refrao|ponte|passagem)"
    r"\s*\d*\s*x?\s*[\]\)\}]?$",
    re.IGNORECASE,
)


def parse_lines(text: str, keep_sections: bool = False) -> tuple[list[str], int]:
    """One lyric per line, blanks dropped, section headers dropped by default."""
    out: list[str] = []
    skipped = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not keep_sections and SECTION_RE.match(line):
            skipped += 1
            continue
        out.append(line)
    return out, skipped


def _guid(*parts: str) -> str:
    """A stable GUID per item.

    Derived from the content rather than random so re-running the generator on
    an unchanged sheet produces a byte-identical file — which is what makes the
    output reviewable in a diff instead of churning on every run.
    """
    h = hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest().upper()
    return f"{{{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}}}"


def _notes_block(text: str, indent: str) -> list[str]:
    """An RPP <NOTES> block.

    Every line is prefixed with `|`, which is what keeps a lyric containing `<`
    or `>` from being read as chunk structure.
    """
    lines = [f"{indent}<NOTES"]
    for piece in text.split("\n"):
        lines.append(f"{indent}  |{piece}")
    lines.append(f"{indent}>")
    return lines


def build_template(song: str, lyrics: list[str], seconds: float,
                   track_name: str) -> str:
    """An empty item per line, laid end to end from 0.

    Empty items — no take, no source. The bridge never looks inside an item,
    only at its position, its length and its notes, so there is nothing for a
    take to carry.
    """
    body: list[str] = [f"<TRACK {_guid(song, track_name)}",
                       f"  NAME {track_name}",
                       "  PEAKCOL 16576",
                       "  BEAT -1",
                       "  AUTOMODE 0",
                       "  VOLPAN 1 0 -1 -1 1",
                       "  MUTESOLO 0 0 0",
                       "  IPHASE 0",
                       "  ISBUS 0 0",
                       "  BUSCOMP 0 0 0 0 0",
                       "  SHOWINMIX 1 0.6667 0.5 1 0.5 0 -1 0",
                       "  SEL 0",
                       "  REC 0 0 1 0 0 0 0 0",
                       "  TRACKHEIGHT 0 0 0 0 0 0"]
    for i, line in enumerate(lyrics):
        pos = i * seconds
        body.append("  <ITEM")
        body.append(f"    POSITION {pos:.14f}")
        body.append(f"    LENGTH {seconds:.14f}")
        body.append("    LOOP 1")
        body.append("    ALLTAKES 0")
        body.append("    FADEIN 1 0 0 1 0 0 0")
        body.append("    FADEOUT 1 0 0 1 0 0 0")
        body.append("    MUTE 0 0")
        body.append("    SEL 0")
        body.append(f"    IGUID {_guid(song, 'i', str(i))}")
        body.append(f"    IID {i + 1}")
        body.extend(_notes_block(line, "    "))
        body.append(f"    GUID {_guid(song, 'g', str(i))}")
        body.append("  >")
    body.append(">")
    return "\n".join(body) + "\n"


def notes_from_template(chunk: str) -> list[str]:
    """Read the notes back out — the inverse of _notes_block.

    Used by the tests: generating a file nobody can read back is how a format
    bug ships. This proves the chunk is balanced and the text survives.
    """
    out: list[str] = []
    depth = 0
    current: list[str] | None = None
    for raw in chunk.splitlines():
        line = raw.strip()
        if current is not None:
            if line == ">":
                out.append("\n".join(current))
                current = None
                depth -= 1
                continue
            current.append(line[1:] if line.startswith("|") else line)
            continue
        if line.startswith("<NOTES"):
            current = []
            depth += 1
        elif line.startswith("<"):
            depth += 1
        elif line == ">":
            depth -= 1
    if depth != 0:
        raise ValueError(f"unbalanced chunk: depth ended at {depth}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Turn lyric .txt files into REAPER track templates."
    )
    ap.add_argument("input", type=Path,
                    help="a .txt file, or a folder of them")
    ap.add_argument("-o", "--output", type=Path, default=Path("reaper_output"),
                    help="where to write the .RTrackTemplate files")
    ap.add_argument("--seconds", type=float, default=4.0,
                    help="length of each line's item (default 4). You will "
                         "resize these against the music anyway; this only "
                         "decides how spread out they start.")
    ap.add_argument("--track", default="Lyrics",
                    choices=["Lyrics", "Chords", "Notes"],
                    help="the track name the template creates (default Lyrics)")
    ap.add_argument("--keep-sections", action="store_true",
                    help="keep lines like 'Chorus' instead of dropping them")
    args = ap.parse_args(argv)

    if args.input.is_dir():
        sources = sorted(args.input.glob("*.txt"))
    elif args.input.is_file():
        sources = [args.input]
    else:
        print(f"not found: {args.input}", file=sys.stderr)
        return 1

    if not sources:
        print(f"no .txt files in {args.input}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    for src in sources:
        lyrics, skipped = parse_lines(
            src.read_text(encoding="utf-8"), args.keep_sections
        )
        if not lyrics:
            print(f"  {src.name}: no lyric lines, skipped")
            continue
        chunk = build_template(src.stem, lyrics, args.seconds, args.track)
        dest = args.output / f"{src.stem}.RTrackTemplate"
        dest.write_text(chunk, encoding="utf-8")
        note = f" ({skipped} section headers dropped)" if skipped else ""
        print(f"  {src.name}: {len(lyrics)} lines -> {dest.name}{note}")

    print(f"\nIn REAPER: Track -> Insert track from template, or drag the "
          f".RTrackTemplate onto the track panel.\nThe track arrives named "
          f"'{args.track}'. Resize the items against the music.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
