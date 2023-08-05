"""Renders SVT Text in a terminal using braille characters.

Renders a page from a list of list of lists of ParsedTile.  Fore- and
background colors are set using terminal escape codes. Double width
text is rendered as bold. Can use either Braille characters or Unicode
13 2x3 box characters.
"""

#  Copyright (C) 2022  Rickard Norlander
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License version 3
#  as published by the Free Software Foundation.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

from typing import List

from svt_text import common

FG_ESCAPES = {
    'K': '\033[35m',
    'R': '\033[91m',
    'G': '\033[92m',
    'B': '\033[38;2;0;50;255m',
    'Y': '\033[93m',
    'M': '\033[95m',
    'C': '\033[96m',
    'W': '\033[97m'
}

BG_ESCAPES = {
    'K': '',
    'R': '\033[41m',
    'G': '\033[102m',
    'B': '\033[44m',
    'Y': '\033[103m',
    'M': '\033[105m',
    'C': '\033[106m',
    'W': '\033[107m',
}

BOLD_ESCAPE = '\033[1m'
RESET_ESCAPE = '\033[0m'

class Style:
    """Terminal character style."""
    def __init__(self, pt):
        self.fg_color = pt.fg_color
        self.bg_color = pt.bg_color
        self.bold = pt.dh_type == common.DH_TRUE

    def as_escapes(self, reset=True):
        return ((RESET_ESCAPE if reset else '') +
                (BG_ESCAPES[self.bg_color] if self.bg_color else '') +
                (FG_ESCAPES[self.fg_color] if self.fg_color else '') +
                (BOLD_ESCAPE if self.bold else ''))

    def __eq__(self, other):
        if other is None:
            return False
        return (self.fg_color == other.fg_color and
                self.bg_color == other.bg_color and
                self.bold == other.bold)

def getboxchar(x: int):
    """Get box character for shape x

    2x3 box characters use the same bit pattern as shape_id, namely

      1  2
      4  8
     16 32

    EXCEPT! That it has gaps corresponding to

    00  10  01  11
    00  10  01  11
    00  10  01  11

    These occur at 21 * n for n=0,1,2,3.  We can use space for the
    first and 2x2 box elements for the rest.
    """
    d, m = divmod(x + 20, 21)
    if m == 20:
        return ' ▌▐█'[d]
    return chr(0x1FB00 + x - d)

def getbraille(x: int):
    """Get braille character for shape x.

    6 dot braille uses the following bit pattern

    1  8
    2 16
    4 32

    Shuffle the bits around and apply the braille offset.
    """
    x = ((x & (1+32)) | ((x & 2) << 2) | ((x & 4) >> 1)
         | ((x & 8) << 1) | ((x & 16) >> 2))
    return chr(10240 + x)

def render_row(parsed_tiles: List[common.ParsedTile]):
    prev_style = None
    for pt in parsed_tiles:
        style = Style(pt)
        if style != prev_style:
            prev_style = style
            print(style.as_escapes(), end='')
        print(pt.char, end='')
    if prev_style is not None:
        print(RESET_ESCAPE, end='')
    print()

def fgbg_fixups(parsed_tiless: List[List[common.ParsedTile]], page: int, subpageid: int):
    """Apply foreground-background shifts.

    In the original page, a white shape on a black background is
    indistinguishable from a black shape on a white background. But
    this is not true when we render. Two reasons: Color and braille.

    The terminal background palette may not be the same as the
    foreground palette. If the rendering uses braille mode, then the
    second issue is that a braille dot will not fully cover the space
    - it will let some background show through. Sometimes a fully
    colored tile may even be rendered as a 6-dot braille on an
    inferred background, for consistency with the surroundings.

    The best looking foreground-background choice must be made. This
    is done heuristically with some manual overrides.
    """
    lastbg = 'K'
    for parsed_tiles in parsed_tiless:
        for parsed_tile in parsed_tiles:
            if not parsed_tile.is_shape_or_space():
                continue

            fg, bg = parsed_tile.fg_color, parsed_tile.bg_color
            if parsed_tile.char == ' ':
                if (bg, lastbg) == ('Y', 'B'):
                    parsed_tile.invert_shape(lastbg)
                elif 401 == page and bg != 'K':
                    parsed_tile.invert_shape('K')
                elif 777 == page and subpageid == 2 and (bg, fg) == ('C', 'K'):
                    parsed_tile.invert_shape('K')
                elif 777 == page and subpageid < 2:
                    lastbg = bg
                elif page not in [129, 149] and bg == 'W':
                    parsed_tile.invert_shape(lastbg)
                else:
                    lastbg = bg
            else:
                if fg == 'K' or bg == 'W':
                    parsed_tile.invert_shape()
                elif (bg, fg) == ('Y', 'B'):
                    parsed_tile.invert_shape()

def remove_fg_back_and_forth(parsed_tiless: List[List[common.ParsedTile]]):
    for parsed_tiles in parsed_tiless:
        for i in range(len(parsed_tiles)):
            if i < 2: continue

            if parsed_tiles[i-1].char != ' ': continue
            if parsed_tiles[i-2].char == ' ' or parsed_tiles[i].char == ' ': continue
            if parsed_tiles[i-2].fg_color != parsed_tiles[i].fg_color: continue
            parsed_tiles[i-1].fg_color = parsed_tiles[i].fg_color

def apply_shapes(parsed_tiless: List[List[common.ParsedTile]], braille: bool):
    for parsed_tiles in parsed_tiless:
        for parsed_tile in parsed_tiles:
            if parsed_tile.is_shape_not_space():
                if braille:
                    parsed_tile.char = getbraille(parsed_tile.shape_id)
                else:
                    parsed_tile.char = getboxchar(parsed_tile.shape_id)


def render_page(parsed_tilesss: List[List[List[common.ParsedTile]]], page: int):
    for subpageid, parsed_tiless in enumerate(parsed_tilesss):
        fgbg_fixups(parsed_tiless, page, subpageid)
        remove_fg_back_and_forth(parsed_tiless)
        apply_shapes(parsed_tiless, common.BRAILLE)
        for parsed_tiles in parsed_tiless:
            render_row(parsed_tiles)
