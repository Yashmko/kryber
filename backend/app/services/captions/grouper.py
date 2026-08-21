"""Caption grouping + deterministic FFmpeg drawtext rendering (§19, §10).

Word timestamps → 2–5 word caption groups → a chain of ``drawtext`` filters
burned into the final MP4. drawtext takes an explicit ``fontfile=`` path, so
the bundled DejaVu Sans Bold TTF is loaded directly (no fontconfig, no tofu
boxes). Text is word-wrapped with PIL-measured pixel widths, centered in the
lower third, faded in/out per group, and the longest "emphasis" word is
highlighted in the brand accent color.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..transcription.base import Segment, Word

_PUNCT_BREAK = re.compile(r"[.!?]+$")

# ── Grouping (unchanged) ─────────────────────────────────────────────────
@dataclass
class CaptionGroup:
    start: float
    end: float
    text: str


def _clip_local_words(words: list[Word], clip_start: float, clip_duration: float) -> list[Word]:
    out: list[Word] = []
    for w in words:
        if not w.word.strip():
            continue
        start = w.start - clip_start
        end = w.end - clip_start
        if end < 0 or start > clip_duration:
            continue
        out.append(Word(word=w.word, start=max(0.0, start), end=min(clip_duration, end)))
    return out


clip_local_words = _clip_local_words


def synthesize_words(segments: list[Segment], clip_start: float, clip_duration: float) -> list[Word]:
    """Fallback when no word timestamps exist: split segment text evenly over time."""
    words: list[Word] = []
    for seg in segments:
        start = seg.start - clip_start
        end = seg.end - clip_start
        if end < 0 or start > clip_duration:
            continue
        start = max(0.0, start)
        end = min(clip_duration, end)
        tokens = seg.text.split()
        if not tokens:
            continue
        step = (end - start) / len(tokens)
        for i, tok in enumerate(tokens):
            words.append(Word(word=tok, start=start + i * step, end=start + (i + 1) * step))
    return words


def group_words(
    words: list[Word],
    *,
    min_words: int = 2,
    max_words: int = 5,
    max_chars: int = 24,
) -> list[CaptionGroup]:
    """Group timestamped words into 2–5 word caption groups."""
    if not words:
        return []

    groups: list[CaptionGroup] = []
    buf: list[Word] = []
    char_count = 0

    def flush() -> None:
        nonlocal buf, char_count
        if buf:
            groups.append(
                CaptionGroup(start=buf[0].start, end=buf[-1].end, text=" ".join(w.word for w in buf))
            )
        buf = []
        char_count = 0

    for w in words:
        buf.append(w)
        char_count += len(w.word) + 1
        end_punct = bool(_PUNCT_BREAK.search(w.word)) if w.word else False
        hit_max = len(buf) >= max_words or char_count > max_chars
        if len(buf) >= min_words and (hit_max or end_punct):
            flush()
    flush()
    return groups


# ── Text normalization (no glyphs the bundled font can't render) ─────────
# ASCII apostrophes are mapped to the typographic RIGHT SINGLE QUOTATION MARK
# (U+2019): visually identical, but NOT a quote character, so it can't break
# ffmpeg's filtergraph quote-balance when the text is embedded in a drawtext
# value. Double quotes and other parser-risky punctuation are dropped.
_UNICODE_MAP = str.maketrans(
    {
        "\u2019": "\u2019",  # keep right single quote
        "\u2018": "\u2019",  # left single quote → right single quote
        "'": "\u2019",       # ASCII apostrophe → right single quote
        "\u201c": "", "\u201d": "", '"': "",  # drop double quotes
        "\u2013": "-", "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\u2022": "-",
    }
)
_ALLOWED = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,!?$%&+=*-\u2019"
)


def normalize_caption_text(text: str) -> str:
    """Uppercase, normalize quotes/dashes, and drop any char DejaVu can't render."""
    text = (text or "").translate(_UNICODE_MAP)
    text = "".join(ch for ch in text if ch in _ALLOWED)
    text = " ".join(text.split())
    return text.upper()


# ── Font resolution ──────────────────────────────────────────────────────
def bundled_font_path() -> str:
    """Absolute path to the bundled caption font (ships with the repo)."""
    path = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
    if path.is_file():
        return str(path)
    system = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if system.is_file():
        return str(system)
    raise FileNotFoundError("Caption font not found (bundled or system).")


# ── drawtext filter generation ───────────────────────────────────────────
try:
    from PIL import ImageFont  # type: ignore
except Exception:  # pragma: no cover
    ImageFont = None

_font_cache: dict = {}


def _get_font(font_path: str, size: int):
    if ImageFont is None:
        raise RuntimeError("Pillow is required for caption rendering.")
    key = (font_path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(font_path, size)
    return _font_cache[key]


def _measure(text: str, font) -> float:
    return font.getlength(text)


def _highlight_word(words: list[str]) -> str | None:
    cands = [w for w in words if len(re.sub(r"[^A-Za-z0-9]", "", w)) >= 3]
    if not cands:
        return None
    return max(cands, key=lambda w: len(re.sub(r"[^A-Za-z0-9]", "", w)))


def _wrap_words(words: list[str], font, max_w: float, space_w: float) -> list[list[str]]:
    lines: list[list[str]] = []
    cur: list[str] = []
    cur_w = 0.0
    for w in words:
        ww = _measure(w, font)
        add = ww + (space_w if cur else 0.0)
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur = [w]
            cur_w = ww
        else:
            cur.append(w)
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def _escape_text(t: str) -> str:
    # After normalize_caption_text, text never contains ASCII quotes.
    # Backslash is still special inside single-quoted drawtext values.
    return t.replace("\\", "\\\\").replace("'", "\u2019")


def _drawtext_filter(
    font_path: str,
    text: str,
    color: str,
    size: int,
    x: int,
    y: int,
    start: float,
    end: float,
    fade: float,
) -> str:
    alpha = f"min(1,min((t-{start:.3f})/{fade:.3f},({end:.3f}-t)/{fade:.3f}))"
    enable = f"between(t,{start:.3f},{end:.3f})"
    return (
        f"drawtext=fontfile='{font_path}':text='{_escape_text(text)}':"
        f"fontcolor={color}:fontsize={size}:"
        f"borderw=5:bordercolor=black@0.9:"
        f"shadowcolor=black@0.6:shadowx=0:shadowy=3:"
        f"x={x}:y={y}:alpha='{alpha}':enable='{enable}':expansion=none"
    )


def build_drawtext_filters(
    groups: list[CaptionGroup],
    *,
    font_path: str | None = None,
    font_size: int = 88,
    width: int = 1080,
    height: int = 1920,
    margin: int = 90,
    bottom_center_y: int = 1460,
    line_spacing: float = 1.18,
    accent_color: str = "0xF65C8B",
) -> str:
    """Return a comma-joined chain of drawtext filters ("" if nothing to draw)."""
    font_path = font_path or bundled_font_path()
    font = _get_font(font_path, font_size)
    space_w = _measure(" ", font)
    max_w = float(width - 2 * margin)

    filters: list[str] = []
    for g in groups:
        text = normalize_caption_text(g.text)
        if not text:
            continue
        words = text.split()
        hl = _highlight_word(words)
        lines = _wrap_words(words, font, max_w, space_w)
        if not lines:
            continue

        line_h = int(font_size * line_spacing)
        total_h = len(lines) * line_h
        start_y = int(bottom_center_y - total_h / 2)
        start = max(0.0, g.start)
        end = max(g.end, g.start + 0.4)
        fade = min(0.12, (end - start) / 2.0) if end > start else 0.05

        for li, line in enumerate(lines):
            segs: list[tuple[str, str]] = []
            for wi, w in enumerate(line):
                t = w + (" " if wi < len(line) - 1 else "")
                color = accent_color if (hl and w == hl) else "white"
                segs.append((t, color))
            total_w = sum(_measure(t, font) for t, _ in segs)
            x0 = (width - total_w) / 2.0
            y = start_y + li * line_h
            xoff = 0.0
            for t, color in segs:
                filters.append(
                    _drawtext_filter(
                        font_path, t, color, font_size, int(x0 + xoff), y, start, end, fade
                    )
                )
                xoff += _measure(t, font)

    return ",".join(filters)
