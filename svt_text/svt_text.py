"""Display svt-text in a terminal.

Example usage:
  svt-text 100
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

import argparse
import configparser
import sys
import os
from typing import List

import requests

from svt_text import common
from svt_text.common import err_print, err_verbose
from svt_text import fetch
from svt_text import render

arg_parser = argparse.ArgumentParser(
    description='Display svt-text in a terminal.', prog='svt-text',
    allow_abbrev=False, prefix_chars='-+')

class YesNo(argparse.Action):
    def __call__(self, parser, namespace, values, option):
        is_negated = option[0] == '+' or option[:5] == '--no-'
        setattr(namespace, self.dest, not is_negated)

def make_yes_no(name, help, short):
    if short is None:
        shorts = []
    else:
        shorts = ['-%s' % short, '+%s' % short]
    arg_parser.add_argument(*shorts, '--%s' % name, '--no-%s' % name,
                            dest=name, nargs=0, action=YesNo, help=help)

arg_parser.add_argument(
    '--cache', metavar='TIME', help='cache pages for N minutes. Inf to always cache')
make_yes_no('braille', 'draw with braille characters, needed if font lacks 2x3 box elements.', None)
arg_parser.add_argument(
    '--version', action='version', version='%(prog)s ' + common.__version__)
make_yes_no('verbose', 'show diagnostic information.', 'v')

def parse_page_range(page_range: str) -> List[int]:
    """Parses the page range command line argument."""
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
    help='either N for a single page, or M-N for a range of pages')
args = argparse.Namespace()

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
        err_print('All pages outside the valid range 100-999.')
        sys.exit(1)

    if invalid_pages and pages:
        err_print('There were pages outside of the valid range 100-999. '
                 'They will be skipped.')
    if not invalid_pages and not pages:
        err_print('No pages to fetch')
    return pages

def get_cache_dir():
    root_cache = os.getenv('XDG_CACHE_HOME')
    if root_cache is None:
        home = os.getenv('HOME', '/tmp')
        root_cache = os.path.join(home, '.cache')
    return os.path.join(root_cache, 'svt-text')

def get_config_paths():
    ret = []
    root_config = os.getenv('XDG_CONFIG_HOME')
    if root_config is None:
        home = os.getenv('HOME')
        if home is not None:
            root_config = os.path.join(home, '.config')
    if root_config is not None:
        ret.append(os.path.join(root_config, 'svt-text', 'config'))
    return ret

def main():
    global args
    args = arg_parser.parse_args()

    config = configparser.ConfigParser()
    config.read(get_config_paths())
    conf_valid = True
    try:
        configcache = config.get('Common', 'cache', fallback=common.CACHE)
        if configcache == 'Inf':
            common.CACHE = 'Inf'
        else:
            common.CACHE = int(configcache)
        common.VERBOSE = config.getboolean('Common', 'verbose', fallback=common.VERBOSE)
        common.BRAILLE = config.getboolean('Common', 'braille', fallback=common.BRAILLE)
    except ValueError:
        err_print('Invalid config file')
        conf_valid = False
    if conf_valid and 'Escapes' in config:
        for k, v in config['Escapes'].items():
            k = k.upper()
            v = v.encode('raw_unicode_escape').decode('unicode_escape')
            if k in render.FG_ESCAPES:
                render.FG_ESCAPES[k] = v
            elif len(k) == 3 and k[:2] == 'BG' and k[2] in render.BG_ESCAPES:
                render.BG_ESCAPES[k[2]] = v
            elif k == 'BOLD':
                render.BOLD_ESCAPE = v

    if args.verbose is not None:
        common.VERBOSE = args.verbose
    if args.braille is not None:
        common.BRAILLE = args.braille
    if args.cache  is not None:
        if args.cache == 'Inf':
            common.CACHE = 'Inf'
        else:
            try:
                common.CACHE = int(args.cache)
            except ValueError:
                err_print('Invalid cache duration')
                arg_parser.print_help()
                sys.exit(1)
    err_verbose('svt-text version %s' % common.__version__)
    cache_dir = get_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    fetcher = fetch.Fetcher(None, cache_dir)
    last_page, next_page = None, None
    fetched_one = False
    showed_one = False
    pages = get_pages_to_fetch()

    err_verbose('Fetching %s pages' % len(pages))
    try:
        for page in pages:
            if next_page is not None and last_page < page < next_page:
                err_verbose('Skipping page %s' % page)
                continue
            next_page, page_info = fetcher.get_page(page)
            last_page = page
            fetched_one = True
            if len(page_info) == 0:
                err_verbose('Page %s was empty' % page)
                continue
            render.render_page(page_info, page)
            showed_one = True
    except requests.exceptions.ConnectionError as err:
        err_print('Fatal error: Failed to download %s' % err.request.url)
        sys.exit(1)
    except fetch.FetchException as err:
        err_print(err.args[0])
        sys.exit(1)

    if fetched_one and not showed_one:
        err_print('All pages were empty')

    sys.exit(0)

if __name__ == '__main__':
    main()
