""" Create a whole new out-of-tree module """

import os
import re
import sys
import distutils
from optparse import OptionGroup

from modtool_base import ModTool

### New out-of-tree-mod module ###############################################
class ModToolNewModule(ModTool):
    """ Create a new out-of-tree module """
    name = 'newmod'
    aliases = ('nm', 'newmodule')
    def __init__(self):
        ModTool.__init__(self)

    def setup_parser(self):
        " Initialise the option parser for 'gr_modtool.py newmod' "
        parser = ModTool.setup_parser(self)
        parser.usage = '%prog rm [options]. \n Call %prog without any options to run it interactively.'
        ogroup = OptionGroup(parser, "New out-of-tree module options")
        ogroup.add_option("-D", "--source-dir", type="string", default=None,
                help="Source directory of the howto example.")
        ogroup.add_option("-l", "--source-dir", type="string", default=None,
                help="Source directory of the howto example.")
        parser.add_option_group(ogroup)
        return parser

    def setup(self):
        def _check_src_dir(srcdir):
            # FIXME Check for correct CMakeLists.txt
            pass
        (options, self.args) = self.parser.parse_args()
        if options.source_dir is None:
            self._info['src_dir'] = raw_input('Source directory of the howto example: ')
            if not _check_src_dir(self._info['src_dir']):
                print "Invalid source directory."
                sys.exit(2)
        if options.block_name is None:
            self._info['src_dir'] = raw_input('Name of the new module: ')
            if not re.match('[a-zA-Z0-9_]+', self._info['modname']):
                print 'Invalid module name.'
                sys.exit(2)
        self._dir = options.directory
        if self._dir is None:
            self._dir = './gr-%s' % self._info['modname']
        try:
            os.stat(self._dir)
        except OSError:
            pass # This is what should happen
        else:
            print 'The given directory exists.'
            sys.exit(2)

    def run(self):
        """ Go, go, go! """
        print "Copying howto example..."
        distutils.dir_util.copy_tree(self._info['src_dir'], self._dir)
        # Remove stuff
        # Set module name in main CMakeLists.txt
        # Are there howtos left? Then replace these




