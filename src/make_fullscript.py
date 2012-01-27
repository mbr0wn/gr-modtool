#!/usr/bin/env python
""" A tool for editing GNU Radio modules. """
# Copyright 2010 Communications Engineering Lab, KIT, Germany
#
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#

import os

LIST_OF_FILES = (
        'util_functions.py',
        'templates.py',
        'code_generator.py',
        'cmakefile_editor.py',
        'modtool_base.py',
        'modtool_add.py',
        'modtool_rm.py',
        'modtool_newmod.py',
        'modtool_help.py',
        'gr_modtool.py')

def append_from_hashtags(fid, newfile):
    """
    Open the file 'newfile', then go through the lines until one
    starts with the sequence '###'. If it does, all lines from here
    are written to the already open file descriptor. """
    f = open(newfile, 'r')
    hash_found = False
    for line in f:
        if line[0:3] == '###':
            hash_found = True
        if hash_found:
            fid.write(line)

def main():
    fid = open('../gr_modtool.py', 'w')
    fid.write(open('fullscript_header.py', 'r').read())
    for fname in LIST_OF_FILES:
        print "Appending %s..." % fname
        append_from_hashtags(fid, fname)
    fid.close()
    print "Making file executable..."
    os.chmod('../gr_modtool.py', 0755)
    print "Done."

if __name__ == '__main__':
    main()

