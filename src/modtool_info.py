""" Returns information about a module """

import os
import sys
from optparse import OptionGroup

from modtool_base import ModTool
from util_functions import get_modname

### Info  module #############################################################
class ModToolInfo(ModTool):
    """ Create a new out-of-tree module """
    name = 'info'
    aliases = ('getinfo', 'inf')
    def __init__(self):
        ModTool.__init__(self)

    def setup_parser(self):
        " Initialise the option parser for 'gr_modtool.py info' "
        parser = ModTool.setup_parser(self)
        parser.usage = '%prog info [options]. \n Call %prog without any options to run it interactively.'
        ogroup = OptionGroup(parser, "Info options")
        ogroup.add_option("--python-readable", action="store_true", default=None,
                help="Return the output in a format that's easier to read for Python scripts.")
        parser.add_option_group(ogroup)
        return parser

    def setup(self):
        # Won't call parent's setup(), because that's too chatty
        (self.options, self.args) = self.parser.parse_args()

    def run(self):
        """ Go, go, go! """
        out_info = {}
        base_dir = os.path.abspath(self.options.directory)
        if self._check_directory(base_dir):
            out_info['base_dir'] = base_dir
        else:
            (up_dir, this_dir) = os.path.split(base_dir)
            if os.path.splitext(up_dir)[1] == 'include':
                up_dir = os.path.splitext(up_dir)[0]
            if self._check_directory(up_dir):
                out_info['base_dir'] = up_dir
            else:
                if self.options.python_readable:
                    print '{}'
                else:
                    print "No module found."
                sys.exit(0)
        os.chdir(out_info['base_dir'])
        out_info['modname'] = get_modname()
        out_info['incdirs'] = []
        mod_incl_dir = os.path.join(out_info['base_dir'], 'include')
        if os.path.isdir(os.path.join(mod_incl_dir, out_info['modname'])):
            out_info['incdirs'].append(os.path.join(mod_incl_dir, out_info['modname']))
        else:
            out_info['incdirs'].append(mod_incl_dir)
        if (os.path.isdir(os.path.join(out_info['base_dir'], 'build'))
                and os.path.isfile(os.path.join(out_info['base_dir'], 'CMakeCache.txt'))):
            out_info['build_dir'] = os.path.join(out_info['base_dir'], 'build')
        else:
            for (dirpath, dirnames, filenames) in os.walk(out_info['base_dir']):
                if 'CMakeCache.txt' in filenames:
                    out_info['build_dir'] = dirpath
                    break
        try:
            cmakecache_fid = open(os.path.join(out_info['build_dir'], 'CMakeCache.txt'))
            for line in cmakecache_fid:
                if line.find('GNURADIO_CORE_INCLUDE_DIRS:PATH') != -1:
                    out_info['incdirs'] += line.replace('GNURADIO_CORE_INCLUDE_DIRS:PATH=', '').strip().split(';')
                if line.find('GRUEL_INCLUDE_DIRS:PATH') != -1:
                    out_info['incdirs'] += line.replace('GRUEL_INCLUDE_DIRS:PATH=', '').strip().split(';')
        except IOError:
            pass
        if self.options.python_readable:
            print str(out_info)
        else:
            self._pretty_print(out_info)

    def _pretty_print(self, out_info):
        """ Output the module info in human-readable format """
        index_names = {'base_dir': 'Base directory',
                       'modname':  'Module name',
                       'build_dir': 'Build directory',
                       'incdirs': 'Include directories'}
        for key in out_info.keys():
            print '%19s: %s' % (index_names[key], out_info[key])

