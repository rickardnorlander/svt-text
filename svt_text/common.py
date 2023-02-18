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

import sys

__version__ = '0.2.0'

# These "constants" are set based on configuration and command line arguments.
VERBOSE = False
BRAILLE = False
CACHE = 1

# Actually constant
DH_FALSE = 0
DH_TRUE = 1
DH_TOP = 2
DH_BOTTOM = 3

class ParsedTile:
    """Data about a parsed tile."""
    def __init__(self, char, shape_id, fg_color, bg_color, dh_type):
        self.char = char
        self.shape_id = shape_id
        self.fg_color = fg_color
        self.bg_color = bg_color
        self.dh_type = dh_type

    def __repr__(self):
        return self.char or str(self.shape_id)

    def copy(self):
        return ParsedTile(self.char, self.shape_id, self.fg_color,
                          self.bg_color, self.dh_type)

    def is_shape_not_space(self):
        return self.shape_id > 0

    def is_shape_or_space(self):
        return self.char == ' ' or self.shape_id > 0

    def invert_shape(self, newbg=None):
        if newbg is None:
            newbg = self.fg_color
        self.fg_color, self.bg_color = self.bg_color, newbg
        self.shape_id = 63 - self.shape_id
        if self.shape_id == 0:
            self.char = ' '
        else:
            self.char = None

def err_print(msg: str):
    """Print a message to stderr"""
    print(msg, file=sys.stderr)

def err_verbose(msg: str):
    """Print a message to stderr if verbose flag is set."""
    if VERBOSE:
        print(msg, file=sys.stderr)
