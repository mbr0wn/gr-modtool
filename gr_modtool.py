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
NEWMOD_TARFILE = """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
X2/T2Yj0QzVbQzHUuPnA0F8zls9dso2hLvjDrti29T4fg+H46z8T7PBz6Q6jlY3CmPtDeyTx0jc+
RvG9i0CkN0lFPSJSjNrqtTVa3Y336JIeEg7GJbdRRebAo5+eSuKSTiteVP2DapLTD57l7lXu8ygg
q4ML73chkMquzsid3d5VZVfBHg4xPdxuMvd3OM4yqvn3vd3d3mV6l+whghIxkkkwvDTYdc3DBxVX
jrPxz0aCR29srqOc0AC9Gkp3lx67D2RyFXEENZYZBe9qOP1Xfat7X978+EzqyacIaNpd6/oG/J6+
3A23uH1hc/nI9Vvr8eZczdnR93OjwG5ufuXPw3DXY9JygYseeLa13ObW91sK5z+T1vnpP5qwvdux
vwdGBIZfJfMjFiHVHXm3bP2fqOaV8XeefieRjjohKTv8sufb+54R68ZPCtOczz7z9PuPVjK54PQI
D9AoXm9KP2dykehexMtlDi/ljl0RYfya9enhrCobtCnxyynl37t118b4QFz+E24Mdd6l9vcx5ePn
9S3DCn6xD546U6ffxM8ZrbxUWxpWr8Oq1+7eavFMiY0yQKSFCRqU0ra80GExj9Q/QwGPByZ9ZRXO
/f7jquZDJBBNiSUzkP9zyL6QUeO9NdYmfwT7T8fKsV3QCJza+2M78hu74K9fqzpyjrGL4z0ibDLy
N6q4+VVppI2fYYbZ5sB+zvU5o65syLgLhcwYDNO2ISe/vndMcjTQlKzUh6894Zs2LZceNjcburDB
erXtSBGA6BJgQOgEUHIGkEZfDWpK65bnLn55P0TzRSlU5LUHdKh5cNXau+cIhqLWyIbpoUsaWTSy
2are+q11XVJSstAIEESECEAmfp+3u0cRigOUEJEcoHM6mIa9xcXoBGAAVABwBCx5Jgl9A7oBEgAc
VQQWMDv9EtOJcvbp6akifXfsCDM3pEGQSSEJGEJbvlt9oz+nowOAQIWkbc60iEiiBw0O9zJiTdWN
2b+zyU51A1PTHKOLBYEE0CDsEJIIAg44cS7N3Wmo9WBhmedrUqruZLViSWYzaKRUIkhsT270KB9h
lAcGMWCEBDRjLLz4Qz5NK3LqIKZE8l73rDOPzfDT338/hbt7Ja9JDvXfzWoIzDkdIhFjsOgoUP7L
HZb7XvcfH29fY5oM/SV94k8cjyxjxPu/ZfvOy/u8I1ym0kz/aYTtLpPj8yb0em2vw9+l/OOOeRwz
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
    if not ((sys.version_info[0] > 2) or
            (sys.version_info[0] == 2 and sys.version_info[1] >= 7)):
        print "Python 2.7 required."
        sys.exit(1)
    main()

