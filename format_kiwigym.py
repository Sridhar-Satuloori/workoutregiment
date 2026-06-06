#!/usr/bin/env python3
"""Format Kiwi Gym workout log into readable markdown."""

import re
from pathlib import Path
from typing import List, Optional, Tuple

TIMING_SUFFIX = re.compile(
    r"\s+("
    r"\d+\s+Rounds(?:\s*/\s*(?:leave every|Leave every|leaving every).*)?"
    r"|\d+\s+minutes(?:\s+AMRAP(?:\s*\([^)]*\))?\.?)?"
    r"|\d+\s+minute(?:\s+Plank)?"
    r"|\d+\s+Rounds\s*/\s*\d+\s+seconds\s+rest"
    r"|\d+\s+Rounds\s*/\s*\d+\s+seconds\s+Rest"
    r"|\d+\s+seconds\s+Rest"
    r"|\*switch.*"
    r")$",
    re.IGNORECASE,
)

SKIP_LINE = re.compile(
    r"^(Thanks for|Don't forget|If you push|If you want|Let me know|"
    r"In case you missed|Are you wanting|Can't make it|Improve your|"
    r"Our latest|Check it out|Legendry|Designed for|It's time|It's really|"
    r"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+|Kiwi Gym Workout Log)|"
    r".*(Thanks for sticking|supporting small businesses|support Kiwi Gym|"
    r"tag us on Instagram|monthly newsletter|The Lifestyle)",
    re.IGNORECASE,
)

PROMO_TAIL = re.compile(
    r"\s+(Can't make it into the gym.*|In case you missed our monthly.*|"
    r"Are you wanting to help support Kiwi Gym.*)$",
    re.IGNORECASE | re.DOTALL,
)


def clean_exercise(text: str) -> str:
    text = re.sub(r"\[http[^\]]*\]", "", text)
    text = re.sub(r"\s*\*+\s*$", "", text)
    text = re.sub(r"^\-\s+", "", text.strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_exercises_and_timing(block: str) -> Tuple[List[str], Optional[str]]:
    block = PROMO_TAIL.sub("", block).strip()
    block = re.sub(r"\s+", " ", block)

    if not block:
        return [], None

    parts = [p.strip() for p in block.split(" + ") if p.strip()]
    if not parts:
        return [], None

    timing = None
    last = parts[-1]
    m = TIMING_SUFFIX.search(last)
    if m:
        timing = m.group(1).strip()
        last = last[: m.start()].strip()
        parts[-1] = last
        if not last:
            parts = parts[:-1]

    # Single-item blocks like "Run - 400 meters 3 Rounds / leave every 4 minutes"
    if len(parts) == 1 and not timing:
        m = TIMING_SUFFIX.search(parts[0])
        if m:
            timing = m.group(1).strip()
            parts[0] = parts[0][: m.start()].strip()

    exercises = [clean_exercise(p) for p in parts if clean_exercise(p)]
    return exercises, timing


def format_block(exercises: List[str], timing: Optional[str]) -> List[str]:
    lines: List[str] = []
    if not exercises and not timing:
        return lines

    for i, ex in enumerate(exercises):
        suffix = " +" if i < len(exercises) - 1 else ""
        lines.append(f"{ex}{suffix}")

    if timing:
        if lines:
            lines.append("")
        # Normalize AMRAP text
        timing = re.sub(
            r"AMRAP\s*\(As many rounds as possible\.\)",
            "AMRAP (as many rounds as possible)",
            timing,
            flags=re.I,
        )
        timing = re.sub(
            r"AMRAP\s*\(as many rounds as possible\.\)",
            "AMRAP (as many rounds as possible)",
            timing,
            flags=re.I,
        )
        if "amrap" in timing.lower() and "(as many rounds as possible)" not in timing.lower():
            timing = timing.replace("AMRAP", "AMRAP (as many rounds as possible)")
            timing = timing.replace("amrap", "AMRAP (as many rounds as possible)")
        lines.append(timing)

    return lines


def format_compact_workout(line: str) -> Optional[str]:
    m = re.match(r"Workout\s+#(\d+)\s+(.*)", line.strip(), re.I)
    if not m:
        return None

    num, rest = m.group(1), m.group(2)
    segments = re.split(r"\s+Then:\s+", rest, flags=re.I)

    out = [f"Workout #{num}", ""]
    first = True

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        exercises, timing = split_exercises_and_timing(segment)
        if not exercises and not timing:
            continue

        if not first:
            out.append("Then:")
            out.append("")
        first = False

        out.extend(format_block(exercises, timing))
        out.append("")

    while out and out[-1] == "":
        out.pop()

    return "\n".join(out)


def parse_email_workout(lines: List[str], start: int) -> Tuple[Optional[str], int]:
    header = lines[start].strip()
    m = re.match(r"Workout\s+#(\d+)\s*$", header, re.I)
    if not m:
        return None, start + 1

    num = m.group(1)
    i = start + 1
    blocks: List[Tuple[List[str], Optional[str]]] = []
    current_exercises: List[str] = []
    current_timing: Optional[str] = None
    seen_then = False

    def flush_block():
        nonlocal current_exercises, current_timing
        if current_exercises or current_timing:
            blocks.append((current_exercises, current_timing))
        current_exercises = []
        current_timing = None

    while i < len(lines):
        raw = lines[i].strip()

        if re.match(r"Workout\s+#\d+", raw, re.I):
            break

        if SKIP_LINE.match(raw) or raw.startswith("http"):
            i += 1
            continue

        if raw == "Then:":
            flush_block()
            seen_then = True
            i += 1
            continue

        if raw in ("+", "-"):
            i += 1
            continue

        if not raw:
            i += 1
            continue

        cleaned = clean_exercise(raw)

        # Footnotes like "*switch sides each round"
        if re.match(r"^\*switch", cleaned, re.I):
            if current_exercises:
                current_exercises[-1] = f"{current_exercises[-1]} ({cleaned.lstrip('*')})"
            else:
                current_timing = cleaned.lstrip("*")
            i += 1
            continue

        # Timing-only lines
        if re.match(
            r"^(\d+\s+(?:Rounds|minutes|minute|seconds)(?:\s*/.*)?|\d+\s+Rounds\s*/.*)$",
            cleaned,
            re.I,
        ):
            current_timing = cleaned
            i += 1
            continue

        # Detail notes like "- 20 seconds work" or "- 100 meters" (not rep counts like "- 10")
        dash_m = re.match(r"^-\s*(.+)$", raw)
        if dash_m:
            note = dash_m.group(1).strip()
            if re.match(r"^\d+\s+(?:seconds?|minutes?|meters?|mile(?:s)?|laps?)\b", note, re.I):
                if current_exercises:
                    current_exercises[-1] = f"{current_exercises[-1]} — {note}"
            i += 1
            continue

        if cleaned:
            current_exercises.append(cleaned)

        i += 1

    flush_block()

    out = [f"Workout #{num}", ""]
    first = True
    for exercises, timing in blocks:
        if not exercises and not timing:
            continue
        if not first:
            out.append("Then:")
            out.append("")
        first = False
        out.extend(format_block(exercises, timing))
        out.append("")

    while out and out[-1] == "":
        out.pop()

    return "\n".join(out), i


def format_file(content: str) -> str:
    lines = content.splitlines()
    workouts: dict[int, str] = {}
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if re.match(r"Workout\s+#\d+\s+\S", line, re.I):
            formatted = format_compact_workout(line)
            if formatted:
                num = int(re.search(r"#(\d+)", formatted).group(1))
                workouts[num] = formatted
            i += 1
            continue

        if re.match(r"Workout\s+#\d+\s*$", line, re.I):
            formatted, next_i = parse_email_workout(lines, i)
            if formatted:
                num = int(re.search(r"#(\d+)", formatted).group(1))
                if num not in workouts:
                    workouts[num] = formatted
            i = next_i
            continue

        i += 1

    parts = ["# Kiwi Gym Workout Log", ""]
    for num in sorted(workouts.keys(), reverse=True):
        parts.append(workouts[num])
        parts.append("")
        parts.append("---")
        parts.append("")

    while parts and parts[-1] == "":
        parts.pop()

    return "\n".join(parts) + "\n"


def main():
    root = Path(__file__).resolve().parent
    src = root / "kiwigymlog.txt"
    dst = root / "kiwigymlog.md"
    txt_dst = root / "kiwigymlog.txt"

    content = src.read_text(encoding="utf-8", errors="replace")
    formatted = format_file(content)
    dst.write_text(formatted, encoding="utf-8")
    txt_dst.write_text(formatted, encoding="utf-8")

    workout_count = formatted.count("Workout #")
    print(f"Formatted {workout_count} workouts -> {dst} and {txt_dst}")
    print(f"Size: {len(content)} -> {len(formatted)} bytes")


if __name__ == "__main__":
    main()
