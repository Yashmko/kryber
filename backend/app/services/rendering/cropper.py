"""9:16 crop planning (§20).

V1 implements a reliable center crop. The architecture leaves room for
person/face tracking: ``x_frac`` (0..1) selects where the 1080-wide window
sits after scaling — a future tracker just supplies a smoothed x_frac per clip.
"""
from __future__ import annotations

TARGET_W = 1080
TARGET_H = 1920


def build_crop_filter(x_frac: float = 0.5) -> str:
    """Return the scale+crop filter chain for a 1080×1920 output.

    ``scale=...force_original_aspect_ratio=increase`` covers 16:9, 4:3, 1:1 and
    9:16 sources; the crop expression picks the horizontal window.
    """
    x_frac = max(0.0, min(1.0, x_frac))
    return (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_W}:{TARGET_H}:'(iw-ow)*{x_frac:.4f}':(ih-oh)/2"
    )
