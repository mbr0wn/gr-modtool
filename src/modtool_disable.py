""" Disable blocks module """

import os
import re
import sys
import glob
from optparse import OptionGroup

from modtool_base import ModTool
from cmakefile_editor import CMakeFileEditor

### Disable module ###########################################################
class ModToolDisable(ModTool):
    """ Disable block (remove CMake entries for files) """
    name = 'disable'
    aliases = ('dis',)
    def __init__(self):
        ModTool.__init__(self)

    def setup_parser(self):
        " Initialise the option parser for 'gr_modtool.py rm' "
        parser = ModTool.setup_parser(self)
        parser.usage = '%prog disable [options]. \n Call %prog without any options to run it interactively.'
        ogroup = OptionGroup(parser, "Disable module options")
        ogroup.add_option("-p", "--pattern", type="string", default=None,
                help="Filter possible choices for blocks to be disabled.")
        ogroup.add_option("-y", "--yes", action="store_true", default=False,
                help="Answer all questions with 'yes'.")
        parser.add_option_group(ogroup)
        return parser

    def setup(self):
        ModTool.setup(self)
        options = self.options
        if options.pattern is not None:
            self._info['pattern'] = options.pattern
        elif options.block_name is not None:
            self._info['pattern'] = options.block_name
        elif len(self.args) >= 2:
            self._info['pattern'] = self.args[1]
        else:
            self._info['pattern'] = raw_input('Which blocks do you want to disable? (Regex): ')
        if len(self._info['pattern']) == 0:
            self._info['pattern'] = '.'
        self._info['yes'] = options.yes

    def run(self):
        """ Go, go, go! """
        def _handle_py_qa(cmake, fname):
            """ Do stuff for py qa """
            cmake.comment_out_lines('GR_ADD_TEST.*'+fname)
        def _handle_cc_qa(cmake, fname):
            """ Do stuff for cc qa """
            cmake.comment_out_lines('add_executable.*'+fname)
            cmake.comment_out_lines('target_link_libraries.*'+os.path.splitext(fname)[0])
            cmake.comment_out_lines('GR_ADD_TEST.*'+os.path.splitext(fname)[0])
        special_treatments = (
                ('python', 'qa.+py$', _handle_py_qa),
                ('lib', 'qa.+\.cc$', _handle_cc_qa),
                )
        for subdir in self._subdirs:
            if self._skip_subdirs[subdir]: continue
            print "Traversing %s..." % subdir
            cmake = CMakeFileEditor(os.path.join(subdir, 'CMakeLists.txt'))
            filenames = cmake.find_filenames_match(self._info['pattern'])
            yes = self._info['yes']
            for fname in filenames:
                file_disabled = False
                if not yes:
                    ans = raw_input("Really disable %s? [Y/n/a/q]: " % fname).lower().strip()
                    if ans == 'a':
                        yes = True
                    if ans == 'q':
                        sys.exit(0)
                    if ans == 'n':
                        continue
                    for special_treatment in special_treatments:
                        if special_treatment[0] == subdir and re.match(special_treatment[1], fname):
                            special_treatment[2](cmake, fname)
                            file_disabled = True
                    if not file_disabled:
                        cmake.disable_file(fname)
            cmake.write()

