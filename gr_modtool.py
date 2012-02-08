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
    open(filename, 'w').write(re.sub(pattern, '', oldfile, flags=re.MULTILINE))

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
    return re.sub('^', '# ', text, flags=re.MULTILINE)

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
        regexp = '(%s\([^()]*?)\s*?(\s?%s)\)' % (entry, to_ignore)
        substi = r'\1' + self.separator + value + r'\2)'
        self.cfile = re.sub(regexp, substi, self.cfile,
                            count=1, flags=re.MULTILINE)

    def remove_value(self, entry, value, to_ignore=''):
        """Remove a value from an entry."""
        regexp = '^\s*(%s\(\s*%s[^()]*?\s*)%s\s*([^()]*\))' % (entry, to_ignore, value)
        self.cfile = re.sub(regexp, r'\1\2', self.cfile, count=1, flags=re.MULTILINE)

    def delete_entry(self, entry, value_pattern=''):
        """Remove an entry from the current buffer."""
        regexp = '%s\s*\([^()]*%s[^()]*\)[^\n]*\n' % (entry, value_pattern)
        self.cfile = re.sub(regexp, '', self.cfile, count=1, flags=re.MULTILINE)

    def write(self):
        """ Write the changes back to the file. """
        open(self.filename, 'w').write(self.cfile)

    def remove_double_newlines(self):
        """Simply clear double newlines from the file buffer."""
        self.cfile = re.sub('\n\n\n+', '\n\n', self.cfile, flags=re.MULTILINE)

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
        swig_block_magic_str = 'GR_SWIG_BLOCK_MAGIC(%s,%s);\n%%include "%s"\n' % (
                                   self._info['modname'],
                                   self._info['blockname'],
                                   self._info['fullblockname'] + '.h')
        if re.search('#include', open(fname_mainswig, 'r').read()):
            append_re_line_sequence(fname_mainswig, '^#include.*\n',
                    '#include "%s.h"' % self._info['fullblockname'])
            append_re_line_sequence(fname_mainswig,
                                    '^GR_SWIG_BLOCK_MAGIC\(.*?\);\s*?\%include.*\s*',
                                    swig_block_magic_str)
        else: # I.e., if the swig file is empty
            oldfile = open(fname_mainswig, 'r').read()
            oldfile = re.sub('^%\{\n', '%%{\n#include "%s.h"\n' % self._info['fullblockname'],
                           oldfile, count=1, flags=re.MULTILINE)
            oldfile = re.sub('^%\}\n', '%}\n\n' + swig_block_magic_str,
                           oldfile, count=1, flags=re.MULTILINE)
            open(fname_mainswig, 'w').write(oldfile)


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
                remove_pattern_from_file('swig/'+self._get_mainswigfile(), '#include "%s"' % f)
        if not self._skip_subdirs['python']:
            py_files_deleted = self._run_subdir('python', ('*.py',), ('GR_PYTHON_INSTALL',))
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
NEWMOD_TARFILE = """QlpoOTFBWSZTWakbzasBovV//f/9Wot///////////////+CJIABB2IEAAgZkIIoKGGbm319L4u5
y+5nkm6a5s68l6IHVzeo7vXz7nZj5vlbmgfAO+Pq+drvs76b7evrN9rsnp7tX0N568x6c0AxwOto
dUgvvnw4HoZgD7067U8S272eAVrT2GSC77uF6YFt9HdGUa3x3AuyQHoruuuKSDu+BZwPWujuskW7
gcujSxqdd3OV3Z27rp3Y6boJMjtjti03wjRewA9VdjoOlcultS18D6AN982xarNmaG+1HIAAEijl
o1QDYrKUAAGMXZ7OnGamNX2ZZVfB52+453tpXzJ6sYHZ8AA7d8Hw3Zt5ObDybopvgWd7z54LvvvH
rtbTyHpx33nvfVXyzt7c0GbardO2S9e+AD23L7nvm33vHnrvcAzQwDm2XO4ddudV7denoOhrwnPT
3NaWWY29m9287t67u6OgMb3eHOuPcGuzm9du973egA99dzr64+dUk+933x3b4T3j6RD1ogQlfYwC
ikF9O566iqgCgF8mEPrPvOPR4qSIJr3e40gW9uqqhA0MoVCo6wQpUUHas9CtVRfXr6ffNFJAvT7o
AAA9HDqREpk2TdndgKk277wHpuwDxL4s5X2ZU6SE9fXOttqBtNqDvbuzeSG0NMDWgZNRIHrpwBIO
2ktsT6fPre1LVNcBc3t95rPmo7fdHffPnx9Nbm6JapbPnYY7zuFw29me4N1SutPAB9x3bXxqnpig
DQAAaD5AAADRNYIAgKo85yAEcECDubQOtAA+Wa8Bo7qyDm404oIu2r2BQ0TscgClU60cAuzaUdhh
6qXrTqkIVfZj3q1Ny7adIqFczW3a+bjzwZGzu3euOaUVXnS7js7uVc6ZoYKeStJbB2ve9147abj0
YQiTrmyjtXdp2aG7A9s096PS6prdhr1r2yynFm97e7va1z02vTp6qdW4ok82utW1tUuew1YLwuA1
2xbZZdJVXnoed2BjKHBhVtWjXLoVQa3aW7YRrrHdUcaadd3cMLoars1wLLuNz0wwtXBsoKhW0Pdt
rsu5EbLCRdRHdbLlO3nZs089q4nYZ3t3olrPZ7619sgAAAFBCopbNB9zA6scAD6VSqDe294wPSX3
O777stw0cOyHUAoAAkUAp2pvA57ojXoNzDyxuZxL3DQepj0tsJswgBEpRRRzGSZhuQZdmq9vbJwB
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
IhCSIMjImopNoNVt+am81WlVr7tae4AICarA6onZHMQ7oGnCuiaJ2kJFjAFRcOUVQw7BXqflp5lb
9FcPKqqqrGyGD493fufh4eed084dMMkbb+2U22264lZI7b2dy6ee2fvaxAkaLuzrpRomosy7uhQW
juxxc40idedra92teMg1JEgR90eSHGAEe+IJxw2TGFoZ8NHp5KvMNjSch0+G3U/B77SyrCnH+46q
dOkMe/Oerti658iqupQQfx7yg8QUSGMBgMGmDG0pRja1RfidUiUaVJZRZppSUlgDRQZKxMsZkky0
iiYFrSEYRI391b4DfWvfOc/SiogmyAkBTULgS6/FCvsn2BAshEAUkg6govE2hGx9hpswfrIqJ4eM
stgeKPD9muM85s1KaunjxjdkAj5Iom3WNakTyYmsuwc7hn81SY++iAS70AjQljbRnaCVGZntdng1
dIClROU1Jw39uHLteV2bPdnv9vPfeduIynlzp48is+Wfk9ikk5Vn5ank0yD9YXxeRUEDi6MGUXQe
Fni8Zod43GodtICUe5AgyARIwiEFGs12GpDShppSJUgA0U0ma1G+fb1401qu/C34fCQW2+I94PeF
VS7X2eHQPPb2eWvjKiARP9/44nVpMsvO+d7dfW8xPr/FfCNqlqgUa+XdloKr39vz37la9fC+H5Hy
Alfd8+3iAAH5nw2reWRJGxqtf0LbbNarq1LamrU1apa1KltU1WWtaW1Naks0kBaANWrFsVrUagvl
3J+x531jx77Sw91yDu31cBju51W+td0nTXruOEABDAd4qnclNWiHeeRdHk0uAyY2PPLPQbxqkqKa
ikKioqKiopNVTg88jx8TrumEhC7jjq2APA88R7XkYg4VFE7HB3cPSdEVFeXnnjt515MXkVAFRUHX
l15DvE0MAE+XUcVPca4Soujh/CIgMHgYED16KxDGLLIAhESIDAyQEEoIp4ICFAIQhejLXv1DbhDy
ogae/IDxz6bJCBnYCVGgg9dgpCZXFZrs8Rh9dHYr7QgsIJCCjQIEJUkQKP+3nwcTCY/vc3vWOaLb
mz6GAxg+3S/pL5E6Gz5lCDTX2y7oczxOTHHOmEDTAmTCH57mfB2kHbevFilj4PZYdwoUshsKQQfx
YCxJNAFkkMl6+Wdgg83jCEDI83jX8MiukTybxyj8NMjFhvaN6hvy4DzGYaqzyIesbpC9Pmi/HQpE
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"""
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
    main()

