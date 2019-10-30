#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Display svt-text in a terminal.

Example usage:
  ./text-tv.py 100
"""

from typing import List, Optional
import re
import sys

try:
    import requests
except ModuleNotFoundError:
    print("'Requests' library is required")
    sys.exit(1)

classTable = {
    #'B'  : '\033[34m',
    #'B'  : '\033[94m',
    # Ubuntu blue is really weird, so specify 24bit color manually.
    # I don't feel great about this solution, may play bad with custom palettes.
    'B': '\033[38;2;0;0;255m',
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


def processSpans(in_html: str) -> str:
    """Converts spans to terminal escapes.

    Converts fore- and background colors from styled spans to terminal escapes.
    Some spans have background images. They are converted to a text
    representation.

    Args:
      in_html: Input html containing spans

    Returns: 
      Partial html. Styled spans converted to characters and ansi escape codes.
    """
    # The idea of this method is as follows. Input consists of spans, and things
    # that are not spans. Spans should be processed, and other things should just
    # be passed through.
    # We iterate over spanny-things. Whenever we find something, we output all
    # text between last span (or beginning of input if no previous) and current
    # span. UNLESS there was a background-image style active. In that case,
    # we instead print special characters meant to imitate the image.
    # At the end we output the text after the last span, if any.

    # This pattern finds all opening and closing span tags.
    c = re.compile('<(?:/)?span(?: class="(?P<classes>[A-Za-z ]*)")?'
                   '(?: style="background: url\(../../images/mos/(?:[A-Z])'
                   '/(?P<number>\d+).gif\)")?>')

    ret = ''
    # Index One after last character of last pattern match, or 0 if there were no
    # previous matches.
    last = 0
    # Keep track of classes of nested spans by pushing previous styles onto a
    # stack, so we can pop when we get a closing tag.
    stack = [[]]  # type: List[List[str]]
    # Keep track of nested background-images.
    bg = [None]  # type: List[Optional[int]]

    for m in c.finditer(in_html):
        # Print things since last spanny thing
        cur_bg = bg[-1]
        if cur_bg is None:
            ret += in_html[last:m.start()]
        else:
            ret += getChar(cur_bg) * (m.start() - last)

        if m.group(0) == '</span>':
            # Restore styles if we have an end-tag.
            ret += '\033[0m'
            stack.pop()
            bg.pop()
            ret += getEscapes(stack[-1])
        else:
            gd = m.groupdict()
            if gd['classes'] is not None:
                new_classes = gd['classes'].split(' ') if gd['classes'] else []
                stack.append(stack[-1] + new_classes)
                ret += getEscapes(new_classes)
            else:
                stack.append(stack[-1])
            if gd['number'] is not None:
                # We have a background image. Push it onto our background image
                # stack.
                bg.append(int(gd['number']))
            else:
                # No background image, still gotta keep the stack the right size.
                bg.append(None)
        last = m.end()
    ret += in_html[last:]
    return ret


def render(html: str) -> None:
    """Takes html of one subpage and renders it."""
    # Handle spans
    html = processSpans(html)
    # Links
    html = re.sub('<a href="\d+.html">', '', html)
    html = re.sub('</a>', '', html)
    # And finally html entities
    out = html.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    print(out)


# Cast to int and back to string to validate the argument is really a number.
n = int(sys.argv[1])
response = requests.get('https://www.svt.se/svttext/tv/pages/'
                        + str(n) + '.html')
if response.status_code != 200:
    friendly = ''
    if response.status_code == 404:
        friendly = ': File not found'
    print('Failed to fetch page. Got %d%s' % (response.status_code, friendly))
    sys.exit(1)
text = response.text

# The first subpage is wrapped in one kind of pre
beforeSplit = text.split('<pre class="root">')
if len(beforeSplit) > 1:
    afterSplit = beforeSplit[1].split('</pre>')
    if len(afterSplit) > 1:
        render(afterSplit[0])

# Subsequent subpages are wrapped in a slightly different kind of pre.
subPages = text.split('<pre class="root sub">')
if len(subPages) > 1:
    for subPage in subPages[1:]:
        # Some breathing room
        print()
        print()
        afterSplit = subPage.split('</pre>')
        if len(afterSplit) > 1:
            render(afterSplit[0])
