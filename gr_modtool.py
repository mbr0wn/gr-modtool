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

import sys
import os
import re
import glob
import base64
import tarfile
from datetime import datetime
from optparse import OptionParser, OptionGroup
from string import Template

### Utility functions ########################################################
def get_command_from_argv(possible_cmds):
    """ Read the requested command from argv. This can't be done with optparse,
    since the option parser isn't defined before the command is known, and
    optparse throws an error."""
    command = None
    for arg in sys.argv:
        if arg[0] == "-":
            continue
        else:
            command = arg
        if command in possible_cmds:
            return arg
    return None

def append_re_line_sequence(filename, linepattern, newline):
    """Detects the re 'linepattern' in the file. After its last occurrence,
    paste 'newline'. If the pattern does not exist, append the new line
    to the file. Then, write. """
    oldfile = open(filename, 'r').read()
    lines = re.findall(linepattern, oldfile, flags=re.MULTILINE)
    if len(lines) == 0:
        open(filename, 'a').write(newline)
        return
    last_line = lines[-1]
    newfile = oldfile.replace(last_line, last_line + newline + '\n')
    open(filename, 'w').write(newfile)

def remove_pattern_from_file(filename, pattern):
    """ Remove all occurrences of a given pattern from a file. """
    oldfile = open(filename, 'r').read()
    pattern = re.compile(pattern, re.MULTILINE)
    open(filename, 'w').write(re.sub(pattern, '', oldfile))

def str_to_fancyc_comment(text):
    """ Return a string as a C formatted comment. """
    l_lines = text.splitlines()
    outstr = "/* " + l_lines[0] + "\n"
    for line in l_lines[1:]:
        outstr += " * " + line + "\n"
    outstr += " */\n"
    return outstr

def str_to_python_comment(text):
    """ Return a string as a Python formatted comment. """
    return re.compile('^', re.MULTILINE).sub('# ', text)

def get_modname():
    """ Grep the current module's name from gnuradio.project """
    try:
        prfile = open('gnuradio.project', 'r').read()
        regexp = r'projectname\s*=\s*([a-zA-Z0-9-_]+)$'
        return re.search(regexp, prfile, flags=re.MULTILINE).group(1).strip()
    except IOError:
        pass
    # OK, there's no gnuradio.project. So, we need to guess.
    cmfile = open('CMakeLists.txt', 'r').read()
    regexp = r'project\s*\(\s*gr-([a-zA-Z0-9-_]+)\s*CXX'
    return re.search(regexp, cmfile, flags=re.MULTILINE).group(1).strip()

def get_class_dict():
    " Return a dictionary of the available commands in the form command->class "
    classdict = {}
    for g in globals().values():
        try:
            if issubclass(g, ModTool):
                classdict[g.name] = g
                for a in g.aliases:
                    classdict[a] = g
        except (TypeError, AttributeError):
            pass
    return classdict

### Templates ################################################################
Templates = {}
# Default licence
Templates['defaultlicense'] = """
Copyright %d <+YOU OR YOUR COMPANY+>.

This is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3, or (at your option)
any later version.

This software is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this software; see the file COPYING.  If not, write to
the Free Software Foundation, Inc., 51 Franklin Street,
Boston, MA 02110-1301, USA.
""" % datetime.now().year

Templates['work_h'] = """
	int work (int noutput_items,
		gr_vector_const_void_star &input_items,
		gr_vector_void_star &output_items);"""

Templates['generalwork_h'] = """
  int general_work (int noutput_items,
		    gr_vector_int &ninput_items,
		    gr_vector_const_void_star &input_items,
		    gr_vector_void_star &output_items);"""

# Header file of a sync/decimator/interpolator block
Templates['block_h'] = Template("""/* -*- c++ -*- */
$license
#ifndef INCLUDED_${fullblocknameupper}_H
#define INCLUDED_${fullblocknameupper}_H

#include <${modname}_api.h>
#include <$grblocktype.h>

class $fullblockname;
typedef boost::shared_ptr<$fullblockname> ${fullblockname}_sptr;

${modnameupper}_API ${fullblockname}_sptr ${modname}_make_$blockname ($arglist);

/*!
 * \\brief <+description+>
 *
 */
class ${modnameupper}_API $fullblockname : public $grblocktype
{
	friend ${modnameupper}_API ${fullblockname}_sptr ${modname}_make_$blockname ($argliststripped);

	$fullblockname ($argliststripped);

 public:
	~$fullblockname ();

$workfunc
};

#endif /* INCLUDED_${fullblocknameupper}_H */

""")


# Work functions for C++ GR blocks
Templates['work_cpp'] = """work (int noutput_items,
			gr_vector_const_void_star &input_items,
			gr_vector_void_star &output_items)
{
	const float *in = (const float *) input_items[0];
	float *out = (float *) output_items[0];

	// Do <+signal processing+>

	// Tell runtime system how many output items we produced.
	return noutput_items;
}
"""

Templates['generalwork_cpp'] = """general_work (int noutput_items,
			       gr_vector_int &ninput_items,
			       gr_vector_const_void_star &input_items,
			       gr_vector_void_star &output_items)
{
  const float *in = (const float *) input_items[0];
  float *out = (float *) output_items[0];

  // Tell runtime system how many input items we consumed on
  // each input stream.
  consume_each (noutput_items);

  // Tell runtime system how many output items we produced.
  return noutput_items;
}
"""

# C++ file of a GR block
Templates['block_cpp'] = Template("""/* -*- c++ -*- */
$license
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <gr_io_signature.h>
#include <$fullblockname.h>


${fullblockname}_sptr
${modname}_make_$blockname ($argliststripped)
{
	return $sptr (new $fullblockname ($arglistnotypes));
}


$fullblockname::$fullblockname ($argliststripped)
	: $grblocktype ("$blockname",
		gr_make_io_signature ($inputsig),
		gr_make_io_signature ($outputsig)$decimation)
{
$constructorcontent}


$fullblockname::~$fullblockname ()
{
}
""")

Templates['block_cpp_workcall'] = Template("""

int
$fullblockname::$workfunc
""")

Templates['block_cpp_hierconstructor'] = """
	connect(self(), 0, d_firstblock, 0);
	// connect other blocks
	connect(d_lastblock, 0, self(), 0);
"""

# Header file for QA
Templates['qa_cmakeentry'] = Template("""
add_executable($basename $filename)
target_link_libraries($basename gnuradio-$modname $${Boost_LIBRARIES})
GR_ADD_TEST($basename $basename)
""")

# C++ file for QA
Templates['qa_cpp'] = Template("""/* -*- c++ -*- */
$license

#include <boost/test/unit_test.hpp>

BOOST_AUTO_TEST_CASE(qa_${fullblockname}_t1){
    BOOST_CHECK_EQUAL(2 + 2, 4);
    // BOOST_* test macros <+here+>
}

BOOST_AUTO_TEST_CASE(qa_${fullblockname}_t2){
    BOOST_CHECK_EQUAL(2 + 2, 4);
    // BOOST_* test macros <+here+>
}

""")

# Python QA code
Templates['qa_python'] = Template("""#!/usr/bin/env python
$license
#

from gnuradio import gr, gr_unittest
import ${modname}$swig

class qa_$blockname (gr_unittest.TestCase):

    def setUp (self):
        self.tb = gr.top_block ()

    def tearDown (self):
        self.tb = None

    def test_001_t (self):
        # set up fg
        self.tb.run ()
        # check data


if __name__ == '__main__':
    gr_unittest.main ()
""")


Templates['hier_python'] = Template('''$license

from gnuradio import gr

class $blockname(gr.hier_block2):
    def __init__(self, $arglist):
    """
    docstring
	"""
        gr.hier_block2.__init__(self, "$blockname",
				gr.io_signature($inputsig),  # Input signature
				gr.io_signature($outputsig)) # Output signature

        # Define blocks
        self.connect()

''')

# Implementation file, C++ header
Templates['impl_h'] = Template('''/* -*- c++ -*- */
$license
#ifndef INCLUDED_QA_${fullblocknameupper}_H
#define INCLUDED_QA_${fullblocknameupper}_H

class $fullblockname
{
 public:
	$fullblockname($arglist);
	~$fullblockname();


 private:

};

#endif /* INCLUDED_${fullblocknameupper}_H */

''')

# Implementation file, C++ source
Templates['impl_cpp'] = Template('''/* -*- c++ -*- */
$license

#include <$fullblockname.h>


$fullblockname::$fullblockname($argliststripped)
{
}


$fullblockname::~$fullblockname()
{
}
''')


Templates['grc_xml'] = Template('''<?xml version="1.0"?>
<block>
  <name>$blockname</name>
  <key>$fullblockname</key>
  <category>$modname</category>
  <import>import $modname</import>
  <make>$modname.$blockname($arglistnotypes)</make>
  <!-- Make one 'param' node for every Parameter you want settable from the GUI.
       Sub-nodes:
       * name
       * key (makes the value accessible as $$keyname, e.g. in the make node)
       * type -->
  <param>
    <name>...</name>
    <key>...</key>
    <type>...</type>
  </param>

  <!-- Make one 'sink' node per input. Sub-nodes:
       * name (an identifier for the GUI)
       * type
       * vlen
       * optional (set to 1 for optional inputs) -->
  <sink>
    <name>in</name>
    <type><!-- e.g. int, real, complex, byte, short, xxx_vector, ...--></type>
  </sink>

  <!-- Make one 'source' node per output. Sub-nodes:
       * name (an identifier for the GUI)
       * type
       * vlen
       * optional (set to 1 for optional inputs) -->
  <source>
    <name>out</name>
    <type><!-- e.g. int, real, complex, byte, short, xxx_vector, ...--></type>
  </source>
</block>
''')

# Usage
Templates['usage'] = """
gr_modtool.py <command> [options] -- Run <command> with the given options.
gr_modtool.py help -- Show a list of commands.
gr_modtool.py help <command> -- Shows the help for a given command. """

### Code generator class #####################################################
class CodeGenerator(object):
    """ Creates the skeleton files. """
    def __init__(self):
        self.defvalpatt = re.compile(" *=[^,)]*")
        self.grtypelist = {
                'sync': 'gr_sync_block',
                'decimator': 'gr_sync_decimator',
                'interpolator': 'gr_sync_interpolator',
                'general': 'gr_block',
                'hiercpp': 'gr_hier_block2',
                'impl': ''}

    def strip_default_values(self, string):
        """ Strip default values from a C++ argument list. """
        return self.defvalpatt.sub("", string)

    def strip_arg_types(self, string):
        """" Strip the argument types from a list of arguments
        Example: "int arg1, double arg2" -> "arg1, arg2" """
        string = self.strip_default_values(string)
        return ", ".join([part.strip().split(' ')[-1] for part in string.split(',')])

    def get_template(self, tpl_id, **kwargs):
        ''' Request a skeleton file from a template.
        First, it prepares a dictionary which the template generator
        can use to fill in the blanks, then it uses Python's
        Template() function to create the file contents. '''
        # Licence
        if tpl_id in ('block_h', 'block_cpp', 'qa_h', 'qa_cpp', 'impl_h', 'impl_cpp'):
            kwargs['license'] = str_to_fancyc_comment(kwargs['license'])
        elif tpl_id in ('qa_python', 'hier_python'):
            kwargs['license'] = str_to_python_comment(kwargs['license'])
        # Standard values for templates
        kwargs['argliststripped'] = self.strip_default_values(kwargs['arglist'])
        kwargs['arglistnotypes'] = self.strip_arg_types(kwargs['arglist'])
        kwargs['fullblocknameupper'] = kwargs['fullblockname'].upper()
        kwargs['modnameupper'] = kwargs['modname'].upper()
        kwargs['grblocktype'] = self.grtypelist[kwargs['blocktype']]
        # Specials for qa_python
        kwargs['swig'] = ''
        if kwargs['blocktype'] != 'hierpython':
            kwargs['swig'] = '_swig'
        # Specials for block_h
        if tpl_id == 'block_h':
            if kwargs['blocktype'] == 'general':
                kwargs['workfunc'] = Templates['generalwork_h']
            elif kwargs['blocktype'] == 'hiercpp':
                kwargs['workfunc'] = ''
            else:
                kwargs['workfunc'] = Templates['work_h']
        # Specials for block_cpp
        if tpl_id == 'block_cpp':
            return self._get_block_cpp(kwargs)
        # All other ones
        return Templates[tpl_id].substitute(kwargs)

    def _get_block_cpp(self, kwargs):
        '''This template is a bit fussy, so it needs some extra attention.'''
        kwargs['decimation'] = ''
        kwargs['constructorcontent'] = ''
        kwargs['sptr'] = kwargs['fullblockname'] + '_sptr'
        if kwargs['blocktype'] == 'decimator':
            kwargs['decimation'] = ", <+decimation+>"
        elif kwargs['blocktype'] == 'interpolator':
            kwargs['decimation'] = ", <+interpolation+>"
        if kwargs['blocktype'] == 'general':
            kwargs['workfunc'] = Templates['generalwork_cpp']
        elif kwargs['blocktype'] == 'hiercpp':
            kwargs['workfunc'] = ''
            kwargs['constructorcontent'] = Templates['block_cpp_hierconstructor']
            kwargs['sptr'] = 'gnuradio::get_initial_sptr'
            return Templates['block_cpp'].substitute(kwargs)
        else:
            kwargs['workfunc'] = Templates['work_cpp']
        return Templates['block_cpp'].substitute(kwargs) + \
               Templates['block_cpp_workcall'].substitute(kwargs)

### CMakeFile.txt editor class ###############################################
class CMakeFileEditor(object):
    """A tool for editing CMakeLists.txt files. """
    def __init__(self, filename, separator=' '):
        self.filename = filename
        fid = open(filename, 'r')
        self.cfile = fid.read()
        self.separator = separator

    def get_entry_value(self, entry, to_ignore=''):
        """ Get the value of an entry.
        to_ignore is the part of the entry you don't care about. """
        regexp = '%s\(%s([^()]+)\)' % (entry, to_ignore)
        mobj = re.search(regexp, self.cfile, flags=re.MULTILINE)
        if mobj is None:
            return None
        value = mobj.groups()[0].strip()
        return value

    def append_value(self, entry, value, to_ignore=''):
        """ Add a value to an entry. """
        regexp = re.compile('(%s\([^()]*?)\s*?(\s?%s)\)' % (entry, to_ignore),
                            re.MULTILINE)
        substi = r'\1' + self.separator + value + r'\2)'
        self.cfile = regexp.sub(substi, self.cfile, count=1)

    def remove_value(self, entry, value, to_ignore=''):
        """Remove a value from an entry."""
        regexp = '^\s*(%s\(\s*%s[^()]*?\s*)%s\s*([^()]*\))' % (entry, to_ignore, value)
        regexp = re.compile(regexp, re.MULTILINE)
        self.cfile = re.sub(regexp, r'\1\2', self.cfile, count=1)

    def delete_entry(self, entry, value_pattern=''):
        """Remove an entry from the current buffer."""
        regexp = '%s\s*\([^()]*%s[^()]*\)[^\n]*\n' % (entry, value_pattern)
        regexp = re.compile(regexp, re.MULTILINE)
        self.cfile = re.sub(regexp, '', self.cfile, count=1)

    def write(self):
        """ Write the changes back to the file. """
        open(self.filename, 'w').write(self.cfile)

    def remove_double_newlines(self):
        """Simply clear double newlines from the file buffer."""
        self.cfile = re.compile('\n\n\n+', re.MULTILINE).sub('\n\n', self.cfile)

### ModTool base class #######################################################
class ModTool(object):
    """ Base class for all modtool command classes. """
    def __init__(self):
        self._subdirs = ['lib', 'include', 'python', 'swig', 'grc'] # List subdirs where stuff happens
        self._has_subdirs = {}
        self._skip_subdirs = {}
        self._info = {}
        for subdir in self._subdirs:
            self._has_subdirs[subdir] = False
            self._skip_subdirs[subdir] = False
        self.parser = self.setup_parser()
        self.tpl = CodeGenerator()
        self.args = None
        self.options = None
        self._dir = None

    def setup_parser(self):
        """ Init the option parser. If derived classes need to add options,
        override this and call the parent function. """
        parser = OptionParser(usage=Templates['usage'], add_help_option=False)
        ogroup = OptionGroup(parser, "General options")
        ogroup.add_option("-h", "--help", action="help", help="Displays this help message.")
        ogroup.add_option("-d", "--directory", type="string", default=".",
                help="Base directory of the module.")
        ogroup.add_option("-n", "--module-name", type="string", default=None,
                help="Name of the GNU Radio module. If possible, this gets detected from CMakeLists.txt.")
        ogroup.add_option("-N", "--block-name", type="string", default=None,
                help="Name of the block, minus the module name prefix.")
        ogroup.add_option("--skip-lib", action="store_true", default=False,
                help="Don't do anything in the lib/ subdirectory.")
        ogroup.add_option("--skip-swig", action="store_true", default=False,
                help="Don't do anything in the swig/ subdirectory.")
        ogroup.add_option("--skip-python", action="store_true", default=False,
                help="Don't do anything in the python/ subdirectory.")
        ogroup.add_option("--skip-grc", action="store_true", default=True,
                help="Don't do anything in the grc/ subdirectory.")
        parser.add_option_group(ogroup)
        return parser


    def setup(self):
        """ Initialise all internal variables, such as the module name etc. """
        (options, self.args) = self.parser.parse_args()
        self._dir = options.directory
        if not self._check_directory(self._dir):
            print "No GNU Radio module found in the given directory. Quitting."
            sys.exit(1)
        print "Operating in directory " + self._dir

        if options.skip_lib:
            print "Force-skipping 'lib'."
            self._skip_subdirs['lib'] = True
        if options.skip_python:
            print "Force-skipping 'python'."
            self._skip_subdirs['python'] = True
        if options.skip_swig:
            print "Force-skipping 'swig'."
            self._skip_subdirs['swig'] = True

        if options.module_name is not None:
            self._info['modname'] = options.module_name
        else:
            self._info['modname'] = get_modname()
        print "GNU Radio module name identified: " + self._info['modname']
        self._info['blockname'] = options.block_name
        self.options = options


    def run(self):
        """ Override this. """
        pass


    def _check_directory(self, directory):
        """ Guesses if dir is a valid GNU Radio module directory by looking for
        gnuradio.project and at least one of the subdirs lib/, python/ and swig/.
        Changes the directory, if valid. """
        has_makefile = False
        try:
            files = os.listdir(directory)
            os.chdir(directory)
        except OSError:
            print "Can't read or chdir to directory %s." % directory
            return False
        for f in files:
            if (os.path.isfile(f) and
                    f == 'CMakeLists.txt' and
                    re.search('find_package\(GnuradioCore\)', open(f).read()) is not None):
                has_makefile = True
            elif os.path.isdir(f):
                if (f in self._has_subdirs.keys()):
                    self._has_subdirs[f] = True
                else:
                    self._skip_subdirs[f] = True
        return bool(has_makefile and (self._has_subdirs.values()))


    def _get_mainswigfile(self):
        """ Find out which name the main SWIG file has. In particular, is it
            a MODNAME.i or a MODNAME_swig.i? Returns None if none is found. """
        modname = self._info['modname']
        swig_files = (modname + '.i',
                      modname + '_swig.i')
        for fname in swig_files:
            if os.path.isfile(os.path.join(self._dir, 'swig', fname)):
                return fname
        return None


### Add new block module #####################################################
class ModToolAdd(ModTool):
    """ Add block to the out-of-tree module. """
    name = 'add'
    aliases = ('insert',)
    _block_types = ('sink', 'source', 'sync', 'decimator', 'interpolator',
                    'general', 'hiercpp', 'hierpython', 'impl')
    def __init__(self):
        ModTool.__init__(self)
        self._info['inputsig'] = "<+MIN_IN+>, <+MAX_IN+>, sizeof (<+float+>)"
        self._info['outputsig'] = "<+MIN_IN+>, <+MAX_IN+>, sizeof (<+float+>)"
        self._add_cc_qa = False
        self._add_py_qa = False


    def setup_parser(self):
        parser = ModTool.setup_parser(self)
        parser.usage = '%prog add [options]. \n Call %prog without any options to run it interactively.'
        ogroup = OptionGroup(parser, "Add module options")
        ogroup.add_option("-t", "--block-type", type="choice",
                choices=self._block_types, default=None, help="One of %s." % ', '.join(self._block_types))
        ogroup.add_option("--license-file", type="string", default=None,
                help="File containing the license header for every source code file.")
        ogroup.add_option("--argument-list", type="string", default=None,
                help="The argument list for the constructor and make functions.")
        ogroup.add_option("--add-python-qa", action="store_true", default=None,
                help="If given, Python QA code is automatically added if possible.")
        ogroup.add_option("--add-cpp-qa", action="store_true", default=None,
                help="If given, C++ QA code is automatically added if possible.")
        ogroup.add_option("--skip-cmakefiles", action="store_true", default=False,
                help="If given, only source files are written, but CMakeLists.txt files are left unchanged.")
        parser.add_option_group(ogroup)
        return parser


    def setup(self):
        ModTool.setup(self)
        options = self.options
        self._info['blocktype'] = options.block_type
        if self._info['blocktype'] is None:
            while self._info['blocktype'] not in self._block_types:
                self._info['blocktype'] = raw_input("Enter code type: ")
                if self._info['blocktype'] not in self._block_types:
                    print 'Must be one of ' + str(self._block_types)
        print "Code is of type: " + self._info['blocktype']

        if (not self._has_subdirs['lib'] and self._info['blocktype'] != 'hierpython') or \
           (not self._has_subdirs['python'] and self._info['blocktype'] == 'hierpython'):
            print "Can't do anything if the relevant subdir is missing. See ya."
            sys.exit(1)

        if self._info['blockname'] is None:
            if len(self.args) >= 2:
                self._info['blockname'] = self.args[1]
            else:
                self._info['blockname'] = raw_input("Enter name of block/code (without module name prefix): ")
        if not re.match('[a-zA-Z0-9_]+', self._info['blockname']):
            print 'Invalid block name.'
            sys.exit(2)
        print "Block/code identifier: " + self._info['blockname']

        self._info['prefix'] = self._info['modname']
        if self._info['blocktype'] == 'impl':
            self._info['prefix'] += 'i'
        self._info['fullblockname'] = self._info['prefix'] + '_' + self._info['blockname']
        print "Full block/code identifier is: " + self._info['fullblockname']

        self._info['license'] = self.setup_choose_license()

        if options.argument_list is not None:
            self._info['arglist'] = options.argument_list
        else:
            self._info['arglist'] = raw_input('Enter valid argument list, including default arguments: ')

        if not (self._info['blocktype'] in ('impl') or self._skip_subdirs['python']):
            self._add_py_qa = options.add_python_qa
            if self._add_py_qa is None:
                self._add_py_qa = (raw_input('Add Python QA code? [Y/n] ').lower() != 'n')
        if not (self._info['blocktype'] in ('hierpython') or self._skip_subdirs['lib']):
            self._add_cc_qa = options.add_cpp_qa
            if self._add_cc_qa is None:
                self._add_cc_qa = (raw_input('Add C++ QA code? [Y/n] ').lower() != 'n')

        if self._info['blocktype'] == 'source':
            self._info['inputsig'] = "0, 0, 0"
            self._info['blocktype'] = "sync"
        if self._info['blocktype'] == 'sink':
            self._info['outputsig'] = "0, 0, 0"
            self._info['blocktype'] = "sync"


    def setup_choose_license(self):
        """ Select a license by the following rules, in this order:
        1) The contents of the file given by --license-file
        2) The contents of the file LICENSE or LICENCE in the modules
           top directory
        3) The default license. """
        if self.options.license_file is not None \
            and os.path.isfile(self.options.license_file):
            return open(self.options.license_file).read()
        elif os.path.isfile('LICENSE'):
            return open('LICENSE').read()
        elif os.path.isfile('LICENCE'):
            return open('LICENCE').read()
        else:
            return Templates['defaultlicense']

    def _write_tpl(self, tpl, path, fname):
        """ Shorthand for writing a substituted template to a file"""
        print "Adding file '%s'..." % fname
        open(os.path.join(path, fname), 'w').write(self.tpl.get_template(tpl, **self._info))

    def run(self):
        """ Go, go, go. """
        if self._info['blocktype'] != 'hierpython' and not self._skip_subdirs['lib']:
            self._run_lib()
        has_swig = self._info['blocktype'] in (
                'sink',
                'source',
                'sync',
                'decimator',
                'interpolator',
                'general',
                'hiercpp') and self._has_subdirs['swig'] and not self._skip_subdirs['swig']
        if has_swig:
            self._run_swig()
        if self._add_py_qa:
            self._run_python_qa()
        if self._info['blocktype'] == 'hierpython':
            self._run_python_hierblock()
        if (not self._skip_subdirs['grc'] and self._has_subdirs['grc'] and
            (self._info['blocktype'] == 'hierpython' or has_swig)):
            self._run_grc()


    def _run_lib(self):
        """ Do everything that needs doing in the subdir 'lib' and 'include'.
        - add .cc and .h files
        - include them into CMakeLists.txt
        - check if C++ QA code is req'd
        - if yes, create qa_*.{cc,h} and add them to CMakeLists.txt
        """
        print "Traversing lib..."
        fname_h = self._info['fullblockname'] + '.h'
        fname_cc = self._info['fullblockname'] + '.cc'
        if self._info['blocktype'] in ('source', 'sink', 'sync', 'decimator',
                                       'interpolator', 'general', 'hiercpp'):
            self._write_tpl('block_h', 'include', fname_h)
            self._write_tpl('block_cpp', 'lib', fname_cc)
        elif self._info['blocktype'] == 'impl':
            self._write_tpl('impl_h', 'include', fname_h)
            self._write_tpl('impl_cpp', 'lib', fname_cc)
        if not self.options.skip_cmakefiles:
            ed = CMakeFileEditor('lib/CMakeLists.txt')
            ed.append_value('add_library', fname_cc)
            ed.write()
            ed = CMakeFileEditor('include/CMakeLists.txt', '\n    ')
            ed.append_value('install', fname_h, 'DESTINATION[^()]+')
            ed.write()

        if not self._add_cc_qa:
            return
        fname_qa_cc = 'qa_%s' % fname_cc
        self._write_tpl('qa_cpp', 'lib', fname_qa_cc)
        if not self.options.skip_cmakefiles:
            open('lib/CMakeLists.txt', 'a').write(Template.substitute(Templates['qa_cmakeentry'],
                                          {'basename': os.path.splitext(fname_qa_cc)[0],
                                           'filename': fname_qa_cc,
                                           'modname': self._info['modname']}))
            ed = CMakeFileEditor('lib/CMakeLists.txt')
            ed.remove_double_newlines()
            ed.write()

    def _run_swig(self):
        """ Do everything that needs doing in the subdir 'swig'.
        - Edit main *.i file
        """
        print "Traversing swig..."
        fname_mainswig = self._get_mainswigfile()
        if fname_mainswig is None:
            print 'Warning: No main swig file found.'
            return
        fname_mainswig = os.path.join('swig', fname_mainswig)
        print "Editing %s..." % fname_mainswig
        swig_block_magic_str = '\nGR_SWIG_BLOCK_MAGIC(%s,%s);\n%%include "%s"\n' % (
                                   self._info['modname'],
                                   self._info['blockname'],
                                   self._info['fullblockname'] + '.h')
        if re.search('#include', open(fname_mainswig, 'r').read()):
            append_re_line_sequence(fname_mainswig, '^#include.*\n',
                    '#include "%s.h"' % self._info['fullblockname'])
        else: # I.e., if the swig file is empty
            oldfile = open(fname_mainswig, 'r').read()
            regexp = re.compile('^%\{\n', re.MULTILINE)
            oldfile = regexp.sub('%%{\n#include "%s.h"\n' % self._info['fullblockname'],
                                 oldfile, count=1)
            open(fname_mainswig, 'w').write(oldfile)
        open(fname_mainswig, 'a').write(swig_block_magic_str)


    def _run_python_qa(self):
        """ Do everything that needs doing in the subdir 'python' to add
        QA code.
        - add .py files
        - include in CMakeLists.txt
        """
        print "Traversing python..."
        fname_py_qa = 'qa_' + self._info['fullblockname'] + '.py'
        self._write_tpl('qa_python', 'python', fname_py_qa)
        os.chmod(os.path.join('python', fname_py_qa), 0755)
        print "Editing python/CMakeLists.txt..."
        open('python/CMakeLists.txt', 'a').write(
                'GR_ADD_TEST(qa_%s ${PYTHON_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/%s)\n' % \
                  (self._info['blockname'], fname_py_qa))

    def _run_python_hierblock(self):
        """ Do everything that needs doing in the subdir 'python' to add
        a Python hier_block.
        - add .py file
        - include in CMakeLists.txt
        """
        print "Traversing python..."
        fname_py = self._info['blockname'] + '.py'
        self._write_tpl('hier_python', 'python', fname_py)
        ed = CMakeFileEditor('python/CMakeLists.txt')
        ed.append_value('GR_PYTHON_INSTALL', fname_py, 'DESTINATION[^()]+')
        ed.write()

    def _run_grc(self):
        """ Do everything that needs doing in the subdir 'grc' to add
        a GRC bindings XML file.
        - add .xml file
        - include in CMakeLists.txt
        """
        print "Traversing grc..."
        fname_grc = self._info['fullblockname'] + '.xml'
        self._write_tpl('grc_xml', 'grc', fname_grc)
        print "Editing grc/CMakeLists.txt..."
        ed = CMakeFileEditor('grc/CMakeLists.txt', '\n    ')
        ed.append_value('install', fname_grc, 'DESTINATION[^()]+')
        ed.write()

### Remove module ###########################################################
class ModToolRemove(ModTool):
    """ Remove block (delete files and remove Makefile entries) """
    name = 'remove'
    aliases = ('rm', 'del')
    def __init__(self):
        ModTool.__init__(self)

    def setup_parser(self):
        " Initialise the option parser for 'gr_modtool.py rm' "
        parser = ModTool.setup_parser(self)
        parser.usage = '%prog rm [options]. \n Call %prog without any options to run it interactively.'
        ogroup = OptionGroup(parser, "Remove module options")
        ogroup.add_option("-p", "--pattern", type="string", default=None,
                help="Filter possible choices for blocks to be deleted.")
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
            self._info['pattern'] = raw_input('Which blocks do you want to delete? (Regex): ')
        if len(self._info['pattern']) == 0:
            self._info['pattern'] = '.'
        self._info['yes'] = options.yes

    def run(self):
        """ Go, go, go! """
        def _remove_cc_test_case(filename=None, ed=None):
            """ Special function that removes the occurrences of a qa*.cc file
            from the CMakeLists.txt. """
            if filename[:2] != 'qa':
                return
            filebase = os.path.splitext(filename)[0]
            ed.delete_entry('add_executable', filebase)
            ed.delete_entry('target_link_libraries', filebase)
            ed.delete_entry('GR_ADD_TEST', filebase)
            ed.remove_double_newlines()

        def _remove_py_test_case(filename=None, ed=None):
            """ Special function that removes the occurrences of a qa*.py file
            from the CMakeLists.txt. """
            if filename[:2] != 'qa':
                return
            filebase = os.path.splitext(filename)[0]
            ed.delete_entry('GR_ADD_TEST', filebase)
            ed.remove_double_newlines()

        def _make_swig_regex(filename):
            filebase = os.path.splitext(filename)[0]
            pyblockname = filebase.replace(self._info['modname'] + '_', '')
            regexp = r'^\s*GR_SWIG_BLOCK_MAGIC\(%s,\s*%s\);\s*%%include\s*"%s"\s*' % \
                    (self._info['modname'], pyblockname, filename)
            return regexp

        if not self._skip_subdirs['lib']:
            self._run_subdir('lib', ('*.cc', '*.h'), ('add_library',),
                             cmakeedit_func=_remove_cc_test_case)
        if not self._skip_subdirs['include']:
            incl_files_deleted = self._run_subdir('include', ('*.cc', '*.h'), ('install',),
                             cmakeedit_func=_remove_cc_test_case)
        if not self._skip_subdirs['swig']:
            for f in incl_files_deleted:
                remove_pattern_from_file('swig/'+self._get_mainswigfile(), _make_swig_regex(f))
                remove_pattern_from_file('swig/'+self._get_mainswigfile(), '#include "%s".*\n' % f)
        if not self._skip_subdirs['python']:
            py_files_deleted = self._run_subdir('python', ('*.py',), ('GR_PYTHON_INSTALL',),
                                                cmakeedit_func=_remove_py_test_case)
            for f in py_files_deleted:
                remove_pattern_from_file('python/__init__.py', '.*import.*%s.*' % f[:-3])
        if not self._skip_subdirs['grc']:
            self._run_subdir('grc', ('*.xml',), ('install',))


    def _run_subdir(self, path, globs, makefile_vars, cmakeedit_func=None):
        """ Delete all files that match a certain pattern in path.
        path - The directory in which this will take place
        globs - A tuple of standard UNIX globs of files to delete (e.g. *.xml)
        makefile_vars - A tuple with a list of CMakeLists.txt-variables which
                        may contain references to the globbed files
        cmakeedit_func - If the CMakeLists.txt needs special editing, use this
        """
        # 1. Create a filtered list
        files = []
        for g in globs:
            files = files + glob.glob("%s/%s"% (path, g))
        files_filt = []
        print "Searching for matching files in %s/:" % path
        for f in files:
            if re.search(self._info['pattern'], os.path.basename(f)) is not None:
                files_filt.append(f)
            if path is "swig":
                files_filt.append(f)
        if len(files_filt) == 0:
            print "None found."
            return []
        # 2. Delete files, Makefile entries and other occurences
        files_deleted = []
        ed = CMakeFileEditor('%s/CMakeLists.txt' % path)
        yes = self._info['yes']
        for f in files_filt:
            b = os.path.basename(f)
            if not yes:
                ans = raw_input("Really delete %s? [Y/n/a/q]: " % f).lower().strip()
                if ans == 'a':
                    yes = True
                if ans == 'q':
                    sys.exit(0)
                if ans == 'n':
                    continue
            files_deleted.append(b)
            print "Deleting %s." % f
            os.unlink(f)
            print "Deleting occurrences of %s from %s/CMakeLists.txt..." % (b, path)
            for var in makefile_vars:
                ed.remove_value(var, b)
            if cmakeedit_func is not None:
                cmakeedit_func(b, ed)
        ed.write()
        return files_deleted


### The entire new module zipfile as base64 encoded tar.bz2  ###
NEWMOD_TARFILE = """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"""
### New out-of-tree-mod module ###############################################
class ModToolNewModule(ModTool):
    """ Create a new out-of-tree module """
    name = 'newmod'
    aliases = ('nm', 'create')
    def __init__(self):
        ModTool.__init__(self)

    def setup_parser(self):
        " Initialise the option parser for 'gr_modtool.py newmod' "
        parser = ModTool.setup_parser(self)
        #parser.usage = '%prog rm [options]. \n Call %prog without any options to run it interactively.'
        #ogroup = OptionGroup(parser, "New out-of-tree module options")
        #parser.add_option_group(ogroup)
        return parser

    def setup(self):
        (options, self.args) = self.parser.parse_args()
        self._info['modname'] = options.module_name
        if self._info['modname'] is None:
            if len(self.args) >= 2:
                self._info['modname'] = self.args[1]
            else:
                self._info['modname'] = raw_input('Name of the new module: ')
        if not re.match('[a-zA-Z0-9_]+', self._info['modname']):
            print 'Invalid module name.'
            sys.exit(2)
        self._dir = options.directory
        if self._dir == '.':
            self._dir = './gr-%s' % self._info['modname']
        print 'Module directory is "%s".' % self._dir
        try:
            os.stat(self._dir)
        except OSError:
            pass # This is what should happen
        else:
            print 'The given directory exists.'
            sys.exit(2)

    def run(self):
        """ Go, go, go! """
        print "Creating directory..."
        try:
            os.mkdir(self._dir)
            os.chdir(self._dir)
        except OSError:
            print 'Could not create directory %s. Quitting.' % self._dir
            sys.exit(2)
        print "Copying howto example..."
        open('tmp.tar.bz2', 'wb').write(base64.b64decode(NEWMOD_TARFILE))
        print "Unpacking..."
        tar = tarfile.open('tmp.tar.bz2', mode='r:bz2')
        tar.extractall()
        tar.close()
        os.unlink('tmp.tar.bz2')
        print "Replacing occurences of 'howto' to '%s'..." % self._info['modname']
        skip_dir_re = re.compile('^..cmake|^..apps|^..grc|doxyxml')
        for root, dirs, files in os.walk('.'):
            if skip_dir_re.search(root):
                continue
            for filename in files:
                f = os.path.join(root, filename)
                s = open(f, 'r').read()
                s = s.replace('howto', self._info['modname'])
                s = s.replace('HOWTO', self._info['modname'].upper())
                open(f, 'w').write(s)
                if filename[0:5] == 'howto':
                    newfilename = filename.replace('howto', self._info['modname'])
                    os.rename(f, os.path.join(root, newfilename))
        print "Done."
        print "Use 'gr_modtool add' to add a new block to this currently empty module."


### Help module ##############################################################
def print_class_descriptions():
    ''' Go through all ModTool* classes and print their name,
        alias and description. '''
    desclist = []
    for gvar in globals().values():
        try:
            if issubclass(gvar, ModTool) and not issubclass(gvar, ModToolHelp):
                desclist.append((gvar.name, ','.join(gvar.aliases), gvar.__doc__))
        except (TypeError, AttributeError):
            pass
    print 'Name      Aliases          Description'
    print '====================================================================='
    for description in desclist:
        print '%-8s  %-12s    %s' % description

class ModToolHelp(ModTool):
    ''' Show some help. '''
    name = 'help'
    aliases = ('h', '?')
    def __init__(self):
        ModTool.__init__(self)

    def setup(self):
        pass

    def run(self):
        cmd_dict = get_class_dict()
        cmds = cmd_dict.keys()
        cmds.remove(self.name)
        for a in self.aliases:
            cmds.remove(a)
        help_requested_for = get_command_from_argv(cmds)
        if help_requested_for is None:
            print 'Usage:' + Templates['usage']
            print '\nList of possible commands:\n'
            print_class_descriptions()
            return
        cmd_dict[help_requested_for]().setup_parser().print_help()

### Main code ################################################################
def main():
    """ Here we go. Parse command, choose class and run. """
    cmd_dict = get_class_dict()
    command = get_command_from_argv(cmd_dict.keys())
    if command is None:
        print 'Usage:' + Templates['usage']
        sys.exit(2)
    modtool = cmd_dict[command]()
    modtool.setup()
    modtool.run()

if __name__ == '__main__':
    if not ((sys.version_info[0] > 2) or
            (sys.version_info[0] == 2 and sys.version_info[1] >= 7)):
        print "Python 2.6 possibly buggy. Ahem."
    main()

