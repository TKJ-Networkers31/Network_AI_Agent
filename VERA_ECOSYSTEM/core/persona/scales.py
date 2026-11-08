"""
core/persona/scales.py — pemilih frasa berdasarkan ambang skor 0-100.

Fungsi murni dan deterministik. Semantik identik dengan `_pick()` lama di
prompt_builder.py: mulai dari entri pertama, naik selama skor >= ambang.
"""

from typing import Sequence


def pick(table: Sequence[tuple[int, str]], value: int) -> str:
    chosen = table[0][1]

    for threshold, text in table:
        if value >= threshold:
            chosen = text
        else:
            break

    return chosen
