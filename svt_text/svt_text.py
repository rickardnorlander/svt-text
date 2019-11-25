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
from typing import List, Tuple
# This is "used" in an annotation in a comment.
from typing import Optional  # pylint: disable=unused-variable,unused-import
import argparse
import re
import sys

try:
    import requests
except ImportError:
    print("'Requests' library is required")
    sys.exit(1)

__version__ = '0.1.3'

arg_parser = argparse.ArgumentParser(
    description='Display svt-text in a terminal.', prog='svt-text',
    allow_abbrev=False)
arg_parser.add_argument(
    '--version', action='version', version='%(prog)s ' + __version__)
arg_parser.add_argument(
    '-v', '--verbose', action='store_true', help='show diagnostic information')


def parse_page_range(page_range: str) -> List[int]:
    try:
        splitted = page_range.split('-')
        if len(splitted) == 1:
            page = int(page_range)
            return [page, page]
        if len(splitted) == 2:
            return [int(x) for x in splitted]
        raise ValueError()
    except ValueError:
        # We can get here from either the int casts or the explicit raise.
        raise argparse.ArgumentTypeError(
            "'%s' is not a valid page range" % page_range)


arg_parser.add_argument(
    'page_range', type=parse_page_range, nargs='+',
    help='Either N for a single page, or M-N for a range of pages')
args = argparse.Namespace()


# See https://en.wikipedia.org/wiki/ANSI_escape_code#Colors
CLASS_TABLE = {
    # 'B': '\033[34m',
    # 'B': '\033[94m',
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


def get_char(image_number: int) -> str:
    """Converts an image number to a character.

    This function is used for handling html like
      <span class="Y" style="background: url(../../images/mos/Y/44.gif)">
    Such spans are used for simple tile-based graphics. In this case 44 would be
    the image number.

    Based on experiments, all images have 2x3 pixels, one bit color depth.
    Valid filename numbers are 32-63 and 96-127. There is a rule for getting the
    image from the number:
    By subtracting 32 from the numbers in the low range, and 64 from the numbers
    in the high range we get a number between 0 and 63. Every bit of that number
    corresponds to a pixel in the following pattern.
      1  2
      4  8
     16 32
    After finding which pixels are set, this function returns a character
    resembling that image.
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


def verbose_print(msg: str):
    if args.verbose:
        print(msg)


def get_escapes(classes: List[str]) -> str:
    """Takes a list of classes, returns string with corresponding escapes.

    This function is used for handling html like <span class="Y">.
    The input is a list of classes, for example ['Y']. Class 'Y' corresponds
    to yellow foreground color, so an escape sequence to set the foreground
    color to yellow is returned.
    In addition to foreground colors, bold and background colors are also
    handled.
    """
    ret = ''
    for _class in classes:
        if _class in CLASS_TABLE:
            ret += CLASS_TABLE[_class]
        else:
            verbose_print('Unknown class %s' % _class)
    return ret


class SVTParser(HTMLParser):
    """Parses an svt-text page, and creates terminal text in self.result

    Takes html from svt-text page.  Converts fore- and background colors from
    styled spans to terminal escapes. Some spans have background images. They
    are converted to a text representation.
    """

    def __init__(self):
        super().__init__()
        self.result = ''

        # Keep track of classes of nested spans by pushing previous styles onto
        # a stack, so we can pop when we get a closing tag.
        self.stack = [[]]  # type: List[List[str]]
        # Keep track of nested background-images.
        self.background = [None]  # type: List[Optional[int]]
        self.background_regex = re.compile(
            r'background: url\(../../images/mos/(?:[A-Z])/(\d+).gif\)')
        self.in_page = False

    def span_enter(self, attrs: List[Tuple[str, str]]):
        new_classes = []  # type: List[str]
        number = None
        for attr in attrs:
            if attr[0] == 'class' and attr[1]:
                new_classes = attr[1].split(' ')
            if attr[0] == 'style':
                match = self.background_regex.match(attr[1])
                if match is not None:
                    number = int(match.group(1))
        self.result += get_escapes(new_classes)
        self.stack.append(self.stack[-1] + new_classes)
        self.background.append(number)

    def span_exit(self):
        # Restore styles
        self.result += '\033[0m'
        self.stack.pop()
        self.background.pop()
        self.result += get_escapes(self.stack[-1])

    def pre_enter(self, attrs: List[Tuple[str, str]]):
        assert not self.in_page
        if attrs == [('class', 'root')]:
            # First page
            self.in_page = True
        elif attrs == [('class', 'root sub')]:
            # Subsequent page
            self.result += '\n\n'
            self.in_page = True

    def pre_exit(self):
        if self.in_page:
            self.in_page = False

    def error(self, message):
        raise NotImplementedError()

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
        cur_bg = self.background[-1]
        if cur_bg is None:
            # We don't have any background image. Just put all data in output
            self.result += data
        else:
            # Replace spaces (that should be all characters) with a character
            # that represents the background image
            replacement = get_char(cur_bg)
            self.result += data.replace(' ', replacement)


EMPTY_PAGE_REGEX = re.compile(
    '^ \\d{3} SVT Text   Sidan ej i sändning  \n\n\n\n\n$\n')


def is_page_empty(parse_result: str) -> bool:
    """Checks whether page is empty.

    Sometimes some page numbers are not in use. When this happens,
    a predictable error message is displayed. Detect that message.
    """
    return bool(EMPTY_PAGE_REGEX.match(parse_result))


NEXT_PAGE_REGEX = re.compile(
    '<script language="JavaScript" type="text/javascript">'
    '<!--var nextPage = "\\d{3}\\.html";'
    'var previousPage = "(\\d{3})\\.html";// --></script>')


class PageSkipper(object):
    """Helper class for skipping non-existent pages.

    When we request a page, whether existent or not, the response
    tells us the previous valid, and the next valid page.
    They are swapped in the response, so we extract 'previousPage' as
    our next_page.
    After requesting page M, and hearing the next valid page is N, we
    store the M, N pair, and skip any pages between M and N. Pages are
    mostly accessed in ascending order, so we don't bother keeping track
    of the previous valid page.
    """

    def __init__(self, page, next_page):
        self.page = page
        self.next_page = next_page

    @classmethod
    def empty(cls):
        return cls(None, None)

    @classmethod
    def fromresponse(cls, current_page: int, response_text: str):
        match = NEXT_PAGE_REGEX.search(response_text)
        if match is None:
            next_page = None
        else:
            next_page = int(match.group(1))
            if next_page == current_page:
                # This happens for the last valid page so set next_page, to
                # 1000 to skip any pages after this.
                next_page = 1000
        return cls(current_page, next_page)

    def should_skip(self, page: int) -> bool:
        if self.next_page is None:
            return False
        return self.page < page < self.next_page


def fetch_page(page: int) -> str:
    response = requests.get('https://www.svt.se/svttext/tv/pages/'
                            + str(page) + '.html')
    if response.status_code != 200:
        friendly = ''
        if response.status_code == 404:
            friendly = ': File not found'
        print('Failed to fetch page. Got %d%s' %
              (response.status_code, friendly))
        # This is unexpected so exit.
        sys.exit(1)
    return response.text


def get_pages_to_fetch() -> List[int]:
    pages = []  # type: List[int]
    invalid_pages = False
    for page_range in args.page_range:
        if page_range[0] < 100:
            page_range[0] = 100
            invalid_pages = True
        if page_range[1] > 999:
            page_range[1] = 999
            invalid_pages = True
        pages.extend(range(page_range[0], page_range[1] + 1))

    if invalid_pages and not pages:
        print('All pages outside the valid range 100-999.')
        sys.exit(1)

    if invalid_pages and pages:
        print('There were pages outside of the valid range 100-999. '
              'They will be skipped.')
    if not invalid_pages and not pages:
        verbose_print('No pages to fetch')
    return pages


def main():
    global args
    args = arg_parser.parse_args()

    pages = get_pages_to_fetch()
    page_skipper = PageSkipper.empty()
    first_page = True
    for page in pages:
        if page_skipper.should_skip(page):
            verbose_print('Skipping page %d' % page)
            continue

        response_text = fetch_page(page)

        page_skipper = PageSkipper.fromresponse(page, response_text)
        parser = SVTParser()
        parser.feed(response_text)
        if is_page_empty(parser.result):
            verbose_print('No page for %d' % page)
            continue

        if not first_page:
            print()
            print()
        print(parser.result)
        first_page = False


if __name__ == '__main__':
    main()
