"""Caption grouping + drawtext filter generation (§19)."""
from __future__ import annotations

from app.services.captions.grouper import (
    CaptionGroup,
    build_drawtext_filters,
    bundled_font_path,
    group_words,
    normalize_caption_text,
    synthesize_words,
)
from app.services.transcription.base import Segment, Word


def test_group_words_two_to_five_words():
    words = [Word(word=w, start=i * 0.5, end=i * 0.5 + 0.4) for i, w in enumerate("one two three four five six seven".split())]
    groups = group_words(words)
    assert all(1 <= len(g.text.split()) <= 5 for g in groups)
    assert " ".join(g.text for g in groups) == "one two three four five six seven"


def test_group_words_breaks_on_punctuation():
    words = [Word(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(["this", "is", "it.", "next", "line"])]
    groups = group_words(words)
    assert groups[0].text == "this is it."
    assert groups[0].end == words[2].end


def test_group_words_empty():
    assert group_words([]) == []


def test_synthesize_words_from_segments():
    segs = [Segment(id=0, start=0, end=3, text="one two three")]
    words = synthesize_words(segs, 0, 3)
    assert [w.word for w in words] == ["one", "two", "three"]
    assert words[0].start == 0
    assert words[-1].end == 3


def test_normalize_caption_text():
    # ASCII apostrophes become the typographic right single quote (visually
    # identical but not a quote char), so drawtext can't break on them.
    assert normalize_caption_text("don't stop") == "DON\u2019T STOP"
    assert normalize_caption_text("don\u2019t stop \u2014 keep\u2026 going") == "DON\u2019T STOP - KEEP... GOING"
    assert normalize_caption_text("  spaced   out  ") == "SPACED OUT"
    # Double quotes and other risky chars are dropped.
    assert normalize_caption_text('say "hi" now') == "SAY HI NOW"
    # Non-renderable glyphs are dropped so captions never show boxes.
    assert normalize_caption_text("caf\u00e9 \U0001F600") == "CAF"


def test_normalized_text_contains_no_ascii_quote():
    assert "'" not in normalize_caption_text("don't can't won't")


def test_bundled_font_exists():
    import os
    assert os.path.isfile(bundled_font_path())


def test_build_drawtext_filters():
    groups = [CaptionGroup(start=0.0, end=1.5, text="I spent three years")]
    f = build_drawtext_filters(groups, font_path=bundled_font_path(), font_size=88)
    assert f.startswith("drawtext=")
    assert "SPENT" in f          # uppercased text present
    assert "fontfile=" in f
    assert "enable='between(t,0.000,1.500)'" in f
    assert "0xF65C8B" in f       # highlight (longest word "YEARS" or "SPENT") colored
    assert "expansion=none" in f


def test_build_drawtext_filters_empty_when_no_text():
    assert build_drawtext_filters([CaptionGroup(0.0, 1.0, "  ")], font_path=bundled_font_path()) == ""
