"""Fetches and interprets SVT Teletext pages.

Fetches web pages corresponding to the teletext pages. A json data
structure is located. Inside is one or more base64-encoded gif images,
each containing a rendered sub page. The images are made up of tiles
of a fixed size where a tile could either be a character, a
decoration, or half a double-height character. The tiles in the image
are converted to monochrome and interpreted by comparing them to
reference tiles.

Example Usage:
  fetcher = Fetcher(None, None)
  fetcher.get_page(100)
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

import base64
import io
import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import PIL
from PIL import Image
import requests

from svt_text import common
import svt_text.generated
from svt_text.common import err_print, err_verbose, ParsedTile
from svt_text.common import DH_FALSE, DH_TRUE, DH_TOP, DH_BOTTOM

TWOP = np.array([1,2,4,8,16,32,64,128], dtype=np.uint8)
SCRIPT_PATTERN = re.compile(
    '<script id="__NEXT_DATA__" type="application/json">(.*)</script></body></html>')

COLOR_TABLE = {
    (0, 0, 0): 'K',
    (255, 0, 0): 'R',
    (0, 255, 0): 'G',
    (0, 0, 255): 'B',
    (255, 255, 0): 'Y',
    (255, 0, 255): 'M',
    (0, 255, 255): 'C',
    (255, 255, 255): 'W'
}
class Tile:
    """A tile from a page-image."""
    def __init__(self, data, key, colors):
        self.data = data
        self.key = key
        self.colors = colors

    @staticmethod
    def from_tile_im(tile_im: Image.Image):
        data = np.asarray(tile_im.getdata())
        color_index_0 = data[0]
        onebit = data == color_index_0
        key = tuple(np.dot(onebit.reshape(-1, 8), TWOP))
        return Tile(None, key, None)

    @staticmethod
    def _lookup_palette(palette: List[int], n: int):
        return (palette[3*n], palette[3*n+1], palette[3*n+2])

    def save(self, fn: str):
        im = Image.fromarray(self.data)
        return im.save(fn)


def merge_doubleheight(top: ParsedTile, bottom: ParsedTile):
    """Merges two halves of a double-height character."""
    assert top.bg_color == bottom.bg_color
    merged = bottom.copy()
    merged.dh_type = DH_TRUE
    if top.char == ' ' and bottom.char == ' ':
        return merged

    if top.char != ' ' and bottom.char != ' ':
        assert top.fg_color == bottom.fg_color

    assert top.is_shape_not_space() == bottom.is_shape_not_space()
    if bottom.is_shape_not_space():
        assert top.shape_id == bottom.shape_id
        return merged

    if top.char != ' ':
        assert top.dh_type == DH_TOP

    if bottom.char != ' ':
        assert bottom.dh_type == DH_BOTTOM

    if top.char == bottom.char:
        return merged

    sub_map = {'Fr': 'F', 'äa': 'ä', 'np': 'p', 'öo': 'ö', 'åa': 'å', 'il': 'i',
               'du': 'd', 'ug': 'y', 'hb': 'b', 'Hn': 'H', 'uv': 'v', 'cs': 's',
               'Yf': 'Y', 'ÖO': 'Ö', 'Tf': 'T', 'FL': 'E', 'Mn': 'M', '8U': '8',
               '35': '3', ' .': '.', ' -': '-', '6U': '6', 'ÄÅ': 'Ä', 'OQ': 'Q',
               'ée': 'é', ' ,': ',', '" ': '"'}
    c = sub_map.get('%s%s' % (top.char, bottom.char))
    if c is not None:
        if bottom.char == ' ':
            merged = top.copy()
            merged.dh_type = DH_TRUE
        merged.char = c
        return merged
    merged.char = '(%s,%s)' % (top.char, bottom.char)
    return merged

def merge_rows(parsed_tiless: List[List[ParsedTile]]):
    """Looks for double-height characters and merges their rows."""
    parsed_tiless2 = []
    for i, parsed_tiles in enumerate(parsed_tiless):
        num_top = sum(pt.dh_type == DH_TOP for pt in parsed_tiles)
        num_bottom = sum(pt.dh_type == DH_BOTTOM for pt in parsed_tiles)
        if num_top == 0 and num_bottom == 0:
            parsed_tiless2.append(parsed_tiles)
            continue
        assert num_bottom == 0 or num_top == 0
        if num_bottom == 0:
            continue
        assert i > 0
        last_pts = parsed_tiless[i-1]
        new_pts = []
        for last_pt, pt in zip(last_pts, parsed_tiles):
            new_pt = merge_doubleheight(last_pt, pt)
            new_pts.append(new_pt)
        parsed_tiless2.append(new_pts)
    return parsed_tiless2

class FetchException(Exception): pass

def index(values, keys):
    # Values is an array of shape[a][b][c]
    # Keys is an array of shape[a][b] where every value is an index into c
    values = values.reshape(-1, values.shape[-1])
    keys = keys.reshape(-1)
    return values[np.arange(keys.size), keys]

def get_tiles(im):
    pal = np.array(im.getpalette()).reshape(256, 3)
    char_palette = [COLOR_TABLE.get(tuple(row), 'K') for row in pal]
    char_palette = np.array(char_palette, dtype=object)

    imdata = np.array(im.getdata())

    width, height = im.size
    tile_width, tile_height = (13, 16)
    num_cols, num_rows = (40, 25)
    assert (width, height) == (tile_width * num_cols, tile_height * num_rows)

    tiles = imdata.reshape((num_rows, tile_height, num_cols, tile_width)).swapaxes(1, 2)
    binary_tiles = (tiles == tiles[:, :, 0:1, 0:1])

    color_0_inds = tiles[:, :, 0, 0]
    color_0 = char_palette[color_0_inds]

    linear_binary_tiles = binary_tiles.reshape(num_rows, num_cols, -1)
    first_different = np.argmin(linear_binary_tiles, axis=2)
    linear_tiles = tiles.reshape(num_rows, num_cols, -1)
    color_1_inds = index(linear_tiles, first_different).reshape(num_rows, num_cols)
    color_1 = char_palette[color_1_inds]

    keys = np.einsum('ijkm,m', binary_tiles.reshape(25, 40, 26, 8), TWOP)

    def make_tile(i, j):
        return Tile(data=binary_tiles[i,j], key=bytes(keys[i, j]),
                    colors=(color_0[i, j], color_1[i, j]))
    return [[make_tile(i, j) for j in range(num_cols)] for i in range(num_rows)]

class Fetcher():
    """Fetches and interprets SVT Teletext pages"""
    def __init__(self, extratiles_dir: Optional[str], cache_dir: Optional[str]):
        self.extratiles_dir = extratiles_dir
        self.cache_dir = cache_dir
        self.known_tiles, self.tile_data = self._read_tile_db()
        self.num_unknown_tiles: Dict[int, int] = {}

    def get_page(self, page_num: int) -> Tuple[int, List[List[List[ParsedTile]]]]:
        """Downloads and interprets a page.

        Returns a nested container of ParsedTile where the dimensions are
        [subpage][row][column]
        """
        response_text = self._download_html(page_num)
        next_page, subpages = self._parse_html(response_text)
        parsed_tilesss = []
        for subpage_num, subpage in enumerate(subpages):
            raw_tiles = get_tiles(subpage)
            parsed_tiless = self._scan_subpage(raw_tiles, page_num, subpage_num)
            parsed_tilesss.append(parsed_tiless)
        if page_num in self.num_unknown_tiles:
            err_print('Page %s has %s unknown tiles.' % (page_num, self.num_unknown_tiles[page_num]))
        return next_page, parsed_tilesss

    def _download_html(self, page: int) -> str:
        if self.cache_dir is not None:
            cache_path = os.path.join(self.cache_dir, str(page) + '.txt')
            try:
                age = (time.time() - os.path.getmtime(cache_path)) / 60
                if common.CACHE == 'Inf' or 0 <= age < common.CACHE:
                    with open(cache_path) as f:
                        ret = f.read()
                        err_verbose('Found page %s in cache' % page)
                        return ret
            except FileNotFoundError:
                pass
        response = requests.get('https://www.svt.se/text-tv/' + str(page))
        if response.status_code != 200:
            friendly = ''
            if response.status_code == 404:
                friendly = ': File not found'
            raise FetchException('Failed to fetch page. Got %d%s' %
                                   (response.status_code, friendly))
        if self.cache_dir is not None:
            with open(cache_path, 'w') as f:
                f.write(response.text)
        return response.text

    def _parse_html(self, response_text: str) -> Tuple[int, List[Image.Image]]:
        m = SCRIPT_PATTERN.search(response_text)
        if m is None:
            raise FetchException('Failed to parse, page had unexpected structure')
        try:
            o = json.loads(m.group(1))
            next_page = o["props"]["pageProps"]["nextPage"]
            if next_page:
                next_page = int(next_page)
            else:
                next_page = 1000

            images = []
            for subpage in o["props"]["pageProps"]["subPages"]:
                base64s = subpage["gifAsBase64"]
                f = io.BytesIO(base64.b64decode(base64s))
                im = Image.open(f)
                if im.size != (520, 400):
                    raise FetchException('Image had unexpected dimensions')
                images.append(im)
        except (KeyError, ValueError):
            raise FetchException('Failed to parse, page had unexpected structure')
        except PIL.UnidentifiedImageError:
            raise FetchException('Unable to decode image')
        return next_page, images

    def _scan_row(self, tile_row: List[Tile], page_num: int,
                  subpage_num: int, row_num: int) -> List[ParsedTile]:
        parsed_tiles = []
        for col_num, tile in enumerate(tile_row):
            if tile.key not in self.known_tiles:
                if self.extratiles_dir is not None:
                    tile.save(
                        "%s/%s-%s-%s-%s.pbm" % (self.extratiles_dir, page_num,
                                                subpage_num, row_num, col_num))
                self.known_tiles.add(tile.key)
            pt = self._tile_db_lookup(tile.key, page_num)
            pt.bg_color = tile.colors[0]
            pt.fg_color = tile.colors[1]
            parsed_tiles.append(pt)

        return parsed_tiles

    def _scan_subpage(self, subpage: List[List[Tile]], page_num: int, subpage_num: int):
        parsed_tiless = []
        for row_num, tile_row in enumerate(subpage):
            parsed_tiles = self._scan_row(tile_row, page_num, subpage_num, row_num)
            parsed_tiless.append(parsed_tiles)
        parsed_tiless = merge_rows(parsed_tiless)
        return parsed_tiless

    def _tile_db_lookup(self, key: Tuple[int, ...], page_num: int):
        tile_data = self.tile_data.get(key)
        if tile_data is None:
            self.num_unknown_tiles[page_num] = self.num_unknown_tiles.get(page_num, 0) + 1
            return ParsedTile(' ', 0 , 'K', 'K', DH_FALSE)
        return tile_data.copy()

    def _read_tile_db(self):
        known_tiles = set()
        tile_data = {}

        def handle_one(fn: str, tile: Tile):
            if len(fn) < 5:
                return
            if tile.key in known_tiles:
                err_verbose('%s is dupe' % fn)
                return
            known_tiles.add(tile.key)
            if fn[:5] == 'slash':
                tile_data[tile.key] = ParsedTile('/', 0, None, None, DH_FALSE)
            if fn[:5] == 'slasT':
                tile_data[tile.key] = ParsedTile('/', 0, None, None, DH_TOP)
            if fn[:5] == 'slasB':
                tile_data[tile.key] = ParsedTile('/', 0, None, None, DH_BOTTOM)
            if fn[:4] == 'char':
                tile_data[tile.key] = ParsedTile(fn[4], 0, None, None, DH_FALSE)
            if fn[:4] == 'topp':
                tile_data[tile.key] = ParsedTile(fn[4], 0, None, None, DH_TOP)
            if fn[:4] == 'bott':
                tile_data[tile.key] = ParsedTile(fn[4], 0, None, None, DH_BOTTOM)
            if fn[:5] == 'shape':
                tile_data[tile.key] = ParsedTile(None, int(fn[5:-4]), None, None, DH_FALSE)

        i = 0
        files = base64.b64decode(svt_text.generated.files)
        for fn in svt_text.generated.names:
            key = files[i*26:i*26+26]
            tile = Tile(None, key, None)
            handle_one(fn, tile)
            i+=1

        if self.extratiles_dir is not None:
            for fn in os.listdir(self.extratiles_dir):
                im = Image.open(os.path.join(self.extratiles_dir, fn))
                tile = Tile.from_tile_im(im)
                handle_one(fn, tile)

        if len(tile_data) == 0:
            err_print('No tiles loaded')
        return known_tiles, tile_data
