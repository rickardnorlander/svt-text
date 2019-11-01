#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Display svt-text in a terminal.

Example usage:
  svt-text 100
"""

#  Copyright (C) 2019  Rickard Norlander
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

from html.parser import HTMLParser
from typing import List, Optional, Tuple
import re
import sys

try:
    import requests
except ModuleNotFoundError:
    print("'Requests' library is required")
    sys.exit(1)

# See https://en.wikipedia.org/wiki/ANSI_escape_code#Colors
classTable = {
    #'B'  : '\033[34m',
    #'B'  : '\033[94m',
    # Ubuntu blue is really weird, so specify 24bit color manually.
    # I don't feel great about this solution, may play bad with custom palettes.
    'B': '\033[38;2;0;50;255m',
    'R': '\033[91m',
    'G': '\033[92m',
    'Y': '\033[93m',
    'M': '\033[95m',
    'C': '\033[96m',
    'W': '\033[97m',
    'bgBK': '\033[40m',
    'bgR': '\033[41m',
    'bgB': '\033[44m',
    'bgG': '\033[102m',
    'bgY': '\033[103m',
    'bgC': '\033[106m',
    'bgW': '\033[107m',
    # Should be double height, but that's not happening. Just bold it.
    'DH': '\033[1m',
}


def getChar(image_number: int) -> str:
    """Converts an image number to a character.

    For instance if filename was 112.gif
    imageNumber is '112'
    Based on experiments the images have 2x3 pixels, one bit color depth.
    Valid filename numbers are 32-63 and 96-127

    By subtracting 32 from the numbers in the low range, and 64 from the numbers
    in the high range we get a number between 0 and 63. Every bit of that number
    corresponds to a pixel in the following pattern.
      1  2
      4  8
     16 32
    """

    if image_number >= 64:
        x = image_number - 64
    else:
        x = image_number - 32

    mode = 'braille'

    if mode == 'braille':
        # 6 dot braille uses the transpose bit pattern
        # 1  8
        # 2 16
        # 4 32
        # So shuffle all the bits around and add the braille offset
        x = ((x & (1+32)) | ((x & 2) << 2) | ((x & 4) >> 1)
                          | ((x & 8) << 1) | ((x & 16) >> 2))
        return chr(10240 + x)
    elif mode == 'boxele':
        # Unicode has 4-pixel box-elements.
        # Convert from 6 pixel to 4 pixel by throwing away middle row.
        x = (x & 3) + (x & 48) // 4
        # The box elements don't seem to have any particular order, so we list
        # them and index.
        return [' ', '▘', '▝', '▀', '▖', '▌', '▞', '▛', '▗', '▚',
                '▐', '▜', '▄', '▙', '▟', '█'][x]
    else:
        if x == '32':
            return ' '
        return '█'


def getEscapes(classes: List[str]) -> str:
    """Takes a list of classes, returns string with corresponding escapes"""
    ret = ''
    for c in classes:
        if c in classTable:
            ret += classTable[c]
    return ret


class SVTParser(HTMLParser):
    """Parses an svt-text page, and creates terminal text in self.s

    Takes html from svt-text page.  Converts fore- and background colors from
    styled spans to terminal escapes. Some spans have background images. They are
    converted to a text representation.
    """

    def __init__(self):
        super().__init__()
        self.s = ''

        # Keep track of classes of nested spans by pushing previous styles onto a
        # stack, so we can pop when we get a closing tag.
        self.stack = [[]]  # type: List[List[str]]
        # Keep track of nested background-images.
        self.bg = [None]  # type: List[Optional[int]]
        self.bg_pattern = re.compile(
            'background: url\(../../images/mos/(?:[A-Z])/(\d+).gif\)')
        self.in_page = False

    def span_enter(self, attrs: List[Tuple[str, str]]):
        new_classes = []  # type: List[str]
        number = None
        for attr in attrs:
            if attr[0] == 'class' and attr[1]:
                new_classes = attr[1].split(' ')
            if attr[0] == 'style':
                m = self.bg_pattern.match(attr[1])
                if m is not None:
                    number = int(m.group(1))
        self.s += getEscapes(new_classes)
        self.stack.append(self.stack[-1] + new_classes)
        self.bg.append(number)

    def span_exit(self):
        # Restore styles
        self.s += '\033[0m'
        self.stack.pop()
        self.bg.pop()
        self.s += getEscapes(self.stack[-1])

    def pre_enter(self, attrs: List[Tuple[str, str]]):
        assert not self.in_page
        if attrs == [('class', 'root')]:
            # First page
            self.in_page = True
        elif attrs == [('class', 'root sub')]:
            # Subsequent page
            self.s += '\n\n'
            self.in_page = True

    def pre_exit(self):
        if self.in_page:
            self.in_page = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]):
        if tag == 'pre':
            self.pre_enter(attrs)
        elif self.in_page and tag == 'span':
            self.span_enter(attrs)

    def handle_endtag(self, tag: str):
        if tag == 'pre':
            self.pre_exit()
        elif self.in_page and tag == 'span':
            self.span_exit()

    def handle_data(self, data: str):
        if not self.in_page:
            return
        cur_bg = self.bg[-1]
        if cur_bg is None:
            # We don't have any background image. Just put all data in output
            self.s += data
        else:
            # Replace spaces (that should be all characters) with a character
            # that represents the background image
            replacement = getChar(cur_bg)
            self.s += data.replace(' ', replacement)


def main():
    # Cast to int and back to string to validate the argument is really a number.
    n = int(sys.argv[1])
    response = requests.get('https://www.svt.se/svttext/tv/pages/'
                            + str(n) + '.html')
    if response.status_code != 200:
        friendly = ''
        if response.status_code == 404:
            friendly = ': File not found'
        print('Failed to fetch page. Got %d%s' %
              (response.status_code, friendly))
        sys.exit(1)

    parser = SVTParser()
    parser.feed(response.text)
    print(parser.s)


if __name__ == '__main__':
    main()
