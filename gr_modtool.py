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
import Cheetah.Template
import xml.etree.ElementTree as ET

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

def strip_default_values(string):
    """ Strip default values from a C++ argument list. """
    return re.sub(' *=[^,)]*', '', string)

def strip_arg_types(string):
    """" Strip the argument types from a list of arguments
    Example: "int arg1, double arg2" -> "arg1, arg2" """
    string = strip_default_values(string)
    return ", ".join([part.strip().split(' ')[-1] for part in string.split(',')])

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

def is_number(s):
    " Return True if the string s contains a number. "
    try:
        float(s)
        return True
    except ValueError:
        return False

def xml_indent(elem, level=0):
    """ Adds indents to XML for pretty printing """
    i = "\n" + level*"    "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            xml_indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i
### Templates ################################################################
Templates = {}
# Default licence
Templates['defaultlicense'] = '''
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
''' % datetime.now().year

# C++ file of a GR block
Templates['block_cpp'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}
\#ifdef HAVE_CONFIG_H
\#include "config.h"
\#endif

\#include <gr_io_signature.h>
\#include "${modname}_${blockname}.h"


${modname}_${blockname}_sptr
${modname}_make_${blockname} (${strip_default_values($arglist)})
{
	return gnuradio::get_initial_sptr (new ${modname}_${blockname}(${strip_arg_types($arglist)}));
}

#if $grblocktype == 'gr_sync_decimator'
#set $decimation = ', <+decimation+>'
#else if $grblocktype == 'gr_sync_interpolator'
#set $decimation = ', <+interpolation+>'
#else
#set $decimation = ''
#end if
/*
 * The private constructor
 */
${modname}_${blockname}::${modname}_${blockname} (${strip_default_values($arglist)})
  : gr_sync_block ("square2_ff",
		   gr_make_io_signature($inputsig),
		   gr_make_io_signature($outputsig)$decimation)
{
#if $grblocktype == 'gr_hier_block2'
		connect(self(), 0, d_firstblock, 0);
		// connect other blocks
		connect(d_lastblock, 0, self(), 0);
#else
	// Put in <+constructor stuff+> here
#end if
}


/*
 * Our virtual destructor.
 */
${modname}_${blockname}::~${modname}_${blockname}()
{
	// Put in <+destructor stuff+> here
}


#if $grblocktype == 'gr_block'
int
${modname}_${blockname}::general_work (int noutput_items,
				   gr_vector_int &ninput_items,
				   gr_vector_const_void_star &input_items,
				   gr_vector_void_star &output_items)
{
	const float *in = (const float *) input_items[0];
	float *out = (float *) output_items[0];

	// Do <+signal processing+>
	// Tell runtime system how many input items we consumed on
	// each input stream.
	consume_each (noutput_items);

	// Tell runtime system how many output items we produced.
	return noutput_items;
}
#else if $grblocktype == 'gr_hier_block2'
#pass
#else
int
${modname}_${blockname}::work(int noutput_items,
		  gr_vector_const_void_star &input_items,
		  gr_vector_void_star &output_items)
{
	const float *in = (const float *) input_items[0];
	float *out = (float *) output_items[0];

	// Do <+signal processing+>

	// Tell runtime system how many output items we produced.
	return noutput_items;
}
#end if

'''

# Block definition header file (for include/)
Templates['block_h'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}

\#ifndef INCLUDED_${modname.upper()}_${blockname.upper()}_H
\#define INCLUDED_${modname.upper()}_${blockname.upper()}_H

\#include <${modname}_api.h>
\#include <${grblocktype}.h>

class ${modname}_${blockname};

typedef boost::shared_ptr<${modname}_${blockname}> ${modname}_${blockname}_sptr;

${modname.upper()}_API ${modname}_${blockname}_sptr ${modname}_make_${blockname} ($arglist);

/*!
 * \\brief <+description+>
 * \ingroup block
 *
 */
class ${modname.upper()}_API ${modname}_${blockname} : public $grblocktype
{
 private:
	friend ${modname.upper()}_API ${modname}_${blockname}_sptr ${modname}_make_square2_ff (${strip_default_values($arglist)});

  ${modname}_${blockname}(${strip_default_values($arglist)});

 public:
  ~${modname}_${blockname}();

#if $grblocktype == 'gr_block'
	// Where all the action really happens
	int general_work (int noutput_items,
	    gr_vector_int &ninput_items,
	    gr_vector_const_void_star &input_items,
	    gr_vector_void_star &output_items);
#else if $grblocktype == 'gr_hier_block2'
#pass
#else
	// Where all the action really happens
	int work (int noutput_items,
	    gr_vector_const_void_star &input_items,
	    gr_vector_void_star &output_items);
#end if
};

#endif /* INCLUDED_${modname.upper()}_${blockname.upper()}_H */

'''

# C++ file for QA
Templates['qa_cpp'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}

\#include <boost/test/unit_test.hpp>

BOOST_AUTO_TEST_CASE(qa_${modname}_${blockname}_t1){
    BOOST_CHECK_EQUAL(2 + 2, 4);
    // TODO BOOST_* test macros here
}

BOOST_AUTO_TEST_CASE(qa_${modname}_${blockname}_t2){
    BOOST_CHECK_EQUAL(2 + 2, 4);
    // TODO BOOST_* test macros here
}

'''


# Python QA code
Templates['qa_python'] = '''\#!/usr/bin/env python
${str_to_python_comment($license)}
#

from gnuradio import gr, gr_unittest
import ${modname}_swig as ${modname}

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
    gr_unittest.run(qa_${blockname}, "qa_${blockname}.xml")
'''


# Hierarchical block, Python version
Templates['hier_python'] = '''${str_to_python_comment($license)}

from gnuradio import gr

class ${blockname}(gr.hier_block2):
    def __init__(self#if $arglist == '' then '' else ', '#$arglist):
    """
    docstring
	"""
        gr.hier_block2.__init__(self, "$blockname",
				gr.io_signature(${inputsig}),  # Input signature
				gr.io_signature(${outputsig})) # Output signature

        # Define blocks and connect them
        self.connect()

'''

# Non-block file, C++ header
Templates['noblock_h'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}
\#ifndef INCLUDED_${modname.upper()}_${blockname.upper()}_H
\#define INCLUDED_${modname.upper()}_${blockname.upper()}_H

\#include <${modname}_api.h>

class ${modname.upper()}_API $blockname
{
	${blockname}(${arglist});
	~${blockname}();
 private:
};

\#endif /* INCLUDED_${modname.upper()}_${blockname.upper()}_H */

'''

# Non-block file, C++ source
Templates['noblock_cpp'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}

\#ifdef HAVE_CONFIG_H
\#include <config.h>
\#endif

\#include <${modname}_${blockname}.h>


$blockname::${blockname}(${strip_default_values($arglist)})
{
}

$blockname::~${blockname}()
{
}

'''


Templates['grc_xml'] = '''<?xml version="1.0"?>
<block>
  <name>$blockname</name>
  <key>${modname}_$blockname</key>
  <category>$modname</category>
  <import>import $modname</import>
  <make>${modname}.${blockname}(${strip_arg_types($arglist)})</make>
  <!-- Make one 'param' node for every Parameter you want settable from the GUI.
       Sub-nodes:
       * name
       * key (makes the value accessible as \$keyname, e.g. in the make node)
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
'''

# Header file for QA
Templates['qa_cmakeentry'] = """
add_executable($basename $filename)
target_link_libraries($basename gnuradio-$modname \${Boost_LIBRARIES})
GR_ADD_TEST($basename $basename)
"""

# Usage
Templates['usage'] = '''
gr_modtool.py <command> [options] -- Run <command> with the given options.
gr_modtool.py help -- Show a list of commands.
gr_modtool.py help <command> -- Shows the help for a given command. '''

### Code generator class #####################################################
class GRMTemplate(Cheetah.Template.Template):
    """ An extended template class """
    def __init__(self, src, searchList=[]):
        self.grtypelist = {
                'sync': 'gr_sync_block',
                'decimator': 'gr_sync_decimator',
                'interpolator': 'gr_sync_interpolator',
                'general': 'gr_block',
                'hiercpp': 'gr_hier_block2',
                'noblock': '',
                'hierpython': ''}
        Cheetah.Template.Template.__init__(self, src, searchList=searchList)
        self.grblocktype = self.grtypelist[searchList['blocktype']]
    def strip_default_values(string):
        """ Strip default values from a C++ argument list. """
        return re.compile(" *=[^,)]*").sub("", string)
    def strip_arg_types(string):
        """" Strip the argument types from a list of arguments
        Example: "int arg1, double arg2" -> "arg1, arg2" """
        string = re.compile(" *=[^,)]*").sub("", string) # FIXME this should call strip_arg_types
        return ", ".join([part.strip().split(' ')[-1] for part in string.split(',')])
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

def get_template(tpl_id, **kwargs):
    """ Return the template given by tpl_id, parsed through Cheetah """
    return str(GRMTemplate(Templates[tpl_id], searchList=kwargs))
### CMakeFile.txt editor class ###############################################
class CMakeFileEditor(object):
    """A tool for editing CMakeLists.txt files. """
    def __init__(self, filename, separator=' ', indent='    '):
        self.filename = filename
        self.cfile = open(filename, 'r').read()
        self.separator = separator
        self.indent = indent

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

    def find_filenames_match(self, regex):
        """ Find the filenames that match a certain regex
        on lines that aren't comments """
        filenames = []
        reg = re.compile(regex)
        fname_re = re.compile('[a-zA-Z]\w+\.\w{1,5}$')
        for line in self.cfile.splitlines():
            if len(line.strip()) == 0 or line.strip()[0] == '#': continue
            for word in re.split('[ /)(\t\n\r\f\v]', line):
                if fname_re.match(word) and reg.search(word):
                    filenames.append(word)
        return filenames

    def disable_file(self, fname):
        """ Comment out a file """
        starts_line = False
        ends_line = False
        for line in self.cfile.splitlines():
            if len(line.strip()) == 0 or line.strip()[0] == '#': continue
            if re.search(r'\b'+fname+r'\b', line):
                if re.match(fname, line.lstrip()):
                    starts_line = True
                if re.search(fname+'$', line.rstrip()):
                    end_line = True
                break
        comment_out_re = r'#\1'
        if not starts_line:
            comment_out_re = r'\n' + self.indent + comment_out_re
        if not ends_line:
            comment_out_re = comment_out_re + '\n' + self.indent
        (self.cfile, nsubs) = re.subn(r'(\b'+fname+r'\b)\s*', comment_out_re, self.cfile)
        if nsubs == 0:
            print "Warning: A replacement failed when commenting out %s. Check the CMakeFile.txt manually." % fname
        elif nsubs > 1:
            print "Warning: Replaced %s %d times (instead of once). Check the CMakeFile.txt manually." % (fname, nsubs)


    def comment_out_lines(self, pattern):
        """ Comments out all lines that match with pattern """
        for line in self.cfile.splitlines():
            if re.search(pattern, line):
                self.cfile = self.cfile.replace(line, '#'+line)

### ModTool base class #######################################################
class ModTool(object):
    """ Base class for all modtool command classes. """
    def __init__(self):
        self._subdirs = ['lib', 'include', 'python', 'swig', 'grc'] # List subdirs where stuff happens
        self._has_subdirs = {}
        self._skip_subdirs = {}
        self._info = {}
        self._file = {}
        for subdir in self._subdirs:
            self._has_subdirs[subdir] = False
            self._skip_subdirs[subdir] = False
        self.parser = self.setup_parser()
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

    def _setup_files(self):
        """ Initialise the self._file[] dictionary """
        self._file['swig'] = os.path.join('swig', self._get_mainswigfile())
        self._file['qalib'] = os.path.join('lib', 'qa_%s.cc' % self._info['modname'])
        self._file['pyinit'] = os.path.join('python', '__init__.py')
        self._file['cmlib'] = os.path.join('lib', 'CMakeLists.txt')
        self._file['cmgrc'] = os.path.join('grc', 'CMakeLists.txt')
        self._file['cmpython'] = os.path.join('python', 'CMakeLists.txt')
        self._file['cminclude'] = os.path.join('include', 'CMakeLists.txt')
        self._file['cmswig'] = os.path.join('swig', 'CMakeLists.txt')

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
        self._setup_files()


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
        mod_info = {}
        base_dir = self._get_base_dir(self.options.directory)
        if base_dir is None:
            if self.options.python_readable:
                print '{}'
            else:
                print "No module found."
            sys.exit(0)
        mod_info['base_dir'] = base_dir
        os.chdir(mod_info['base_dir'])
        mod_info['modname'] = get_modname()
        mod_info['incdirs'] = []
        mod_incl_dir = os.path.join(mod_info['base_dir'], 'include')
        if os.path.isdir(os.path.join(mod_incl_dir, mod_info['modname'])):
            mod_info['incdirs'].append(os.path.join(mod_incl_dir, mod_info['modname']))
        else:
            mod_info['incdirs'].append(mod_incl_dir)
        build_dir = self._get_build_dir(mod_info)
        if build_dir is not None:
            mod_info['build_dir'] = build_dir
            mod_info['incdirs'] += self._get_include_dirs(mod_info)
        if self.options.python_readable:
            print str(mod_info)
        else:
            self._pretty_print(mod_info)

    def _get_base_dir(self, start_dir):
        """ Figure out the base dir (where the top-level cmake file is) """
        base_dir = os.path.abspath(start_dir)
        if self._check_directory(base_dir):
            return base_dir
        else:
            (up_dir, this_dir) = os.path.split(base_dir)
            if os.path.split(up_dir)[1] == 'include':
                up_dir = os.path.split(up_dir)[0]
            if self._check_directory(up_dir):
                return up_dir
        return None

    def _get_build_dir(self, mod_info):
        """ Figure out the build dir (i.e. where you run 'cmake'). This checks
        for a file called CMakeCache.txt, which is created when running cmake.
        If that hasn't happened, the build dir cannot be detected, unless it's
        called 'build', which is then assumed to be the build dir. """
        has_build_dir = os.path.isdir(os.path.join(mod_info['base_dir'], 'build'))
        if (has_build_dir and os.path.isfile(os.path.join(mod_info['base_dir'], 'CMakeCache.txt'))):
            return os.path.join(mod_info['base_dir'], 'build')
        else:
            for (dirpath, dirnames, filenames) in os.walk(mod_info['base_dir']):
                if 'CMakeCache.txt' in filenames:
                    return dirpath
        if has_build_dir:
            return os.path.join(mod_info['base_dir'], 'build')
        return None

    def _get_include_dirs(self, mod_info):
        """ Figure out include dirs for the make process. """
        inc_dirs = []
        try:
            cmakecache_fid = open(os.path.join(mod_info['build_dir'], 'CMakeCache.txt'))
            for line in cmakecache_fid:
                if line.find('GNURADIO_CORE_INCLUDE_DIRS:PATH') != -1:
                    inc_dirs += line.replace('GNURADIO_CORE_INCLUDE_DIRS:PATH=', '').strip().split(';')
                if line.find('GRUEL_INCLUDE_DIRS:PATH') != -1:
                    inc_dirs += line.replace('GRUEL_INCLUDE_DIRS:PATH=', '').strip().split(';')
        except IOError:
            pass
        return inc_dirs

    def _pretty_print(self, mod_info):
        """ Output the module info in human-readable format """
        index_names = {'base_dir': 'Base directory',
                       'modname':  'Module name',
                       'build_dir': 'Build directory',
                       'incdirs': 'Include directories'}
        for key in mod_info.keys():
            print '%19s: %s' % (index_names[key], mod_info[key])

### Add new block module #####################################################
class ModToolAdd(ModTool):
    """ Add block to the out-of-tree module. """
    name = 'add'
    aliases = ('insert',)
    _block_types = ('sink', 'source', 'sync', 'decimator', 'interpolator',
                    'general', 'hiercpp', 'hierpython', 'noblock')
    def __init__(self):
        ModTool.__init__(self)
        self._info['inputsig'] = "<+MIN_IN+>, <+MAX_IN+>, sizeof (<+float+>)"
        self._info['outputsig'] = "<+MIN_OUT+>, <+MAX_OUT+>, sizeof (<+float+>)"
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
        open(os.path.join(path, fname), 'w').write(get_template(tpl, **self._info))

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
        elif self._info['blocktype'] == 'noblock':
            self._write_tpl('noblock_h', 'include', fname_h)
            self._write_tpl('noblock_cpp', 'lib', fname_cc)
        if not self.options.skip_cmakefiles:
            ed = CMakeFileEditor(self._file['cmlib'])
            ed.append_value('add_library', fname_cc)
            ed.write()
            ed = CMakeFileEditor(self._file['cminclude'], '\n    ')
            ed.append_value('install', fname_h, 'DESTINATION[^()]+')
            ed.write()
        if not self._add_cc_qa:
            return
        fname_qa_cc = 'qa_%s' % fname_cc
        self._write_tpl('qa_cpp', 'lib', fname_qa_cc)
        if not self.options.skip_cmakefiles:
            open('lib/CMakeLists.txt', 'a').write(
                    str(
                        Cheetah.Template.Template(
                            Templates['qa_cmakeentry'],
                            searchList={'basename': os.path.splitext(fname_qa_cc)[0],
                                        'filename': fname_qa_cc,
                                        'modname': self._info['modname']
                                       }
                        )
                     )
            )
            ed = CMakeFileEditor(self._file['cmlib'])
            ed.remove_double_newlines()
            ed.write()

    def _run_swig(self):
        """ Do everything that needs doing in the subdir 'swig'.
        - Edit main *.i file
        """
        print "Traversing swig..."
        print "Editing %s..." % self._file['swig']
        swig_block_magic_str = '\nGR_SWIG_BLOCK_MAGIC(%s,%s);\n%%include "%s"\n' % (
                                   self._info['modname'],
                                   self._info['blockname'],
                                   self._info['fullblockname'] + '.h')
        if re.search('#include', open(self._file['swig'], 'r').read()):
            append_re_line_sequence(self._file['swig'], '^#include.*\n',
                    '#include "%s.h"' % self._info['fullblockname'])
        else: # I.e., if the swig file is empty
            oldfile = open(self._file['swig'], 'r').read()
            regexp = re.compile('^%\{\n', re.MULTILINE)
            oldfile = regexp.sub('%%{\n#include "%s.h"\n' % self._info['fullblockname'],
                                 oldfile, count=1)
            open(self._file['swig'], 'w').write(oldfile)
        open(self._file['swig'], 'a').write(swig_block_magic_str)


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
        open(self._file['cmpython'], 'a').write(
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
        ed = CMakeFileEditor(self._file['cmpython'])
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
        ed = CMakeFileEditor(self._file['cmgrc'], '\n    ')
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
                remove_pattern_from_file(self._file['swig'], _make_swig_regex(f))
                remove_pattern_from_file(self._file['swig'], '#include "%s".*\n' % f)
        if not self._skip_subdirs['python']:
            py_files_deleted = self._run_subdir('python', ('*.py',), ('GR_PYTHON_INSTALL',),
                                                cmakeedit_func=_remove_py_test_case)
            for f in py_files_deleted:
                remove_pattern_from_file(self._file['pyinit'], '.*import.*%s.*' % f[:-3])
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


### Disable module ###########################################################
class ModToolDisable(ModTool):
    """ Disable block (comments out CMake entries for files) """
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
            return True
        def _handle_py_mod(cmake, fname):
            """ Do stuff for py extra files """
            try:
                initfile = open(self._file['pyinit']).read()
            except IOError:
                return False
            pymodname = os.path.splitext(fname)[0]
            initfile = re.sub(r'((from|import)\s+\b'+pymodname+r'\b)', r'#\1', initfile)
            open(self._file['pyinit'], 'w').write(initfile)
            return False
        def _handle_cc_qa(cmake, fname):
            """ Do stuff for cc qa """
            cmake.comment_out_lines('add_executable.*'+fname)
            cmake.comment_out_lines('target_link_libraries.*'+os.path.splitext(fname)[0])
            cmake.comment_out_lines('GR_ADD_TEST.*'+os.path.splitext(fname)[0])
            return True
        def _handle_h_swig(cmake, fname):
            """ Comment out include files from the SWIG file,
            as well as the block magic """
            swigfile = open(self._file['swig']).read()
            (swigfile, nsubs) = re.subn('(.include\s+"'+fname+'")', r'//\1', swigfile)
            if nsubs > 0:
                print "Changing %s..." % self._file['swig']
            if nsubs > 1: # Need to find a single BLOCK_MAGIC
                blockname = os.path.splitext(fname[len(self._info['modname'])+1:])[0] # DEPRECATE 3.7
                (swigfile, nsubs) = re.subn('(GR_SWIG_BLOCK_MAGIC.+'+blockname+'.+;)', r'//\1', swigfile)
                if nsubs > 1:
                    print "Hm, something didn't go right while editing %s." % self._file['swig']
            open(self._file['swig'], 'w').write(swigfile)
            return False
        def _handle_i_swig(cmake, fname):
            """ Comment out include files from the SWIG file,
            as well as the block magic """
            swigfile = open(self._file['swig']).read()
            blockname = os.path.splitext(fname[len(self._info['modname'])+1:])[0]
            swigfile = re.sub('(%include\s+"'+fname+'")', r'//\1', swigfile)
            print "Changing %s..." % self._file['swig']
            swigfile = re.sub('(GR_SWIG_BLOCK_MAGIC.+'+blockname+'.+;)', r'//\1', swigfile)
            open(self._file['swig'], 'w').write(swigfile)
            return False
        # List of special rules: 0: subdir, 1: filename re match, 2: function
        special_treatments = (
                ('python', 'qa.+py$', _handle_py_qa),
                ('python', '^(?!qa).+py$', _handle_py_mod),
                ('lib', 'qa.+\.cc$', _handle_cc_qa),
                ('include', '.+\.h$', _handle_h_swig),
                ('swig', '.+\.i$', _handle_i_swig)
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
                        file_disabled = special_treatment[2](cmake, fname)
                if not file_disabled:
                    cmake.disable_file(fname)
            cmake.write()
        print "Careful: gr_modtool disable does not resolve dependencies."

### The entire new module zipfile as base64 encoded tar.bz2  ###
NEWMOD_TARFILE = """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
DxfqQV/+ou5IpwoSDjfiJyA="""
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
        print "Replacing occurences of 'howto' to '%s'..." % self._info['modname'],
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


### Parser for CC blocks ####################################################
def dummy_translator(the_type, default_v=None):
    """ Doesn't really translate. """
    return the_type

class ParserCCBlock(object):
    """ Class to read blocks written in C++ """
    def __init__(self, filename_cc, filename_h, blockname, type_trans=dummy_translator):
        self.code_cc = open(filename_cc).read()
        self.code_h  = open(filename_h).read()
        self.blockname = blockname
        self.type_trans = type_trans

    def read_io_signature(self):
        """ Scans a .cc file for an IO signature. """
        def _figure_out_iotype_and_vlen(iosigcall, typestr):
            """ From a type identifier, returns the data type.
            E.g., for sizeof(int), it will return 'int'.
            Returns a list! """
            if 'gr_make_iosignaturev' in iosigcall:
                print 'tbi'
                raise ValueError
            return {'type': [_typestr_to_iotype(x) for x in typestr.split(',')],
                    'vlen': [_typestr_to_vlen(x)   for x in typestr.split(',')]
                   }
        def _typestr_to_iotype(typestr):
            """ Convert a type string (e.g. sizeof(int) * vlen) to the type (e.g. 'int'). """
            type_match = re.search('sizeof\s*\(([^)]*)\)', typestr)
            if type_match is None:
                return self.type_trans('char')
            return self.type_trans(type_match.group(1))
        def _typestr_to_vlen(typestr):
            """ From a type identifier, returns the vector length of the block's
            input/out. E.g., for 'sizeof(int) * 10', it returns 10. For
            'sizeof(int)', it returns '1'. For 'sizeof(int) * vlen', it returns
            the string vlen. """
            # Catch fringe case where no sizeof() is given
            if typestr.find('sizeof') == -1:
                return typestr
            if typestr.find('*') == -1:
                return '1'
            vlen_parts = typestr.split('*')
            for fac in vlen_parts:
                if fac.find('sizeof') != -1:
                    vlen_parts.remove(fac)
            if len(vlen_parts) == 1:
                return vlen_parts[0].strip()
            elif len(vlen_parts) > 1:
                return '*'.join(vlen_parts).strip()
        iosig = {}
        iosig_regex = '(?P<incall>gr_make_io_signature[23v]?)\s*\(\s*(?P<inmin>[^,]+),\s*(?P<inmax>[^,]+),' + \
                      '\s*(?P<intype>(\([^\)]*\)|[^)])+)\),\s*' + \
                      '(?P<outcall>gr_make_io_signature[23v]?)\s*\(\s*(?P<outmin>[^,]+),\s*(?P<outmax>[^,]+),' + \
                      '\s*(?P<outtype>(\([^\)]*\)|[^)])+)\)'
        iosig_match = re.compile(iosig_regex, re.MULTILINE).search(self.code_cc)
        try:
            iosig['in'] = _figure_out_iotype_and_vlen(iosig_match.group('incall'),
                                                      iosig_match.group('intype'))
            iosig['in']['min_ports'] = iosig_match.group('inmin')
            iosig['in']['max_ports'] = iosig_match.group('inmax')
        except ValueError, Exception:
            print "Error: Can't parse input signature."
        try:
            iosig['out'] = _figure_out_iotype_and_vlen(iosig_match.group('outcall'),
                                                       iosig_match.group('outtype'))
            iosig['out']['min_ports'] = iosig_match.group('outmin')
            iosig['out']['max_ports'] = iosig_match.group('outmax')
        except ValueError, Exception:
            print "Error: Can't parse output signature."
        return iosig

    def read_params(self):
        """ Read the parameters required to initialize the block """
        make_regex = '(?<=_API)\s+\w+_sptr\s+\w+_make_\w+\s*\(([^)]*)\)'
        make_match = re.compile(make_regex, re.MULTILINE).search(self.code_h)
        # Go through params
        params = []
        try:
            param_str = make_match.group(1).strip()
            if len(param_str) == 0:
                return params
            for param in param_str.split(','):
                p_split = param.strip().split('=')
                if len(p_split) == 2:
                    default_v = p_split[1].strip()
                else:
                    default_v = ''
                (p_type, p_name) = [x for x in p_split[0].strip().split() if x != '']
                params.append({'key': p_name,
                               'type': self.type_trans(p_type, default_v),
                               'default': default_v,
                               'in_constructor': True})
        except ValueError:
            print "Error: Can't parse this: ", make_match.group(0)
            sys.exit(1)
        return params

### GRC XML Generator ########################################################
try:
    import lxml.etree
    LXML_IMPORTED = True
except ImportError:
    LXML_IMPORTED = False

class GRCXMLGenerator(object):
    """ Create and write the XML bindings for a GRC block. """
    def __init__(self, modname=None, blockname=None, doc=None, params=None, iosig=None):
        """docstring for __init__"""
        params_list = ['$'+s['key'] for s in params if s['in_constructor']]
        self._header = {'name': blockname.capitalize(),
                        'key': '%s_%s' % (modname, blockname),
                        'category': modname.upper(),
                        'import': 'import %s' % modname,
                        'make': '%s.%s(%s)' % (modname, blockname, ', '.join(params_list))
                       }
        self.params = params
        self.iosig = iosig
        self.doc = doc
        self.root = None
        if LXML_IMPORTED:
            self._prettyprint = self._lxml_prettyprint
        else:
            self._prettyprint = self._manual_prettyprint

    def _lxml_prettyprint(self):
        """ XML pretty printer using lxml """
        return lxml.etree.tostring(
                   lxml.etree.fromstring(ET.tostring(self.root, encoding="UTF-8")),
                   pretty_print=True
               )

    def _manual_prettyprint(self):
        """ XML pretty printer using xml_indent """
        xml_indent(self.root)
        return ET.tostring(self.root, encoding="UTF-8")

    def make_xml(self):
        """ Create the actual tag tree """
        root = ET.Element("block")
        iosig = self.iosig
        for tag in self._header.keys():
            this_tag = ET.SubElement(root, tag)
            this_tag.text = self._header[tag]
        for param in self.params:
            param_tag = ET.SubElement(root, 'param')
            ET.SubElement(param_tag, 'name').text = param['key'].capitalize()
            ET.SubElement(param_tag, 'key').text = param['key']
            ET.SubElement(param_tag, 'type').text = param['type']
            if len(param['default']):
                ET.SubElement(param_tag, 'value').text = param['default']
        for inout in sorted(iosig.keys()):
            if iosig[inout]['max_ports'] == '0':
                continue
            for i in range(len(iosig[inout]['type'])):
                s_tag = ET.SubElement(root, {'in': 'sink', 'out': 'source'}[inout])
                ET.SubElement(s_tag, 'name').text = inout
                ET.SubElement(s_tag, 'type').text = iosig[inout]['type'][i]
                if iosig[inout]['vlen'][i] != '1':
                    vlen = iosig[inout]['vlen'][i]
                    if is_number(vlen):
                        ET.SubElement(s_tag, 'vlen').text = vlen
                    else:
                        ET.SubElement(s_tag, 'vlen').text = '$'+vlen
                if i == len(iosig[inout]['type'])-1:
                    if not is_number(iosig[inout]['max_ports']):
                        ET.SubElement(s_tag, 'nports').text = iosig[inout]['max_ports']
                    elif len(iosig[inout]['type']) < int(iosig[inout]['max_ports']):
                        ET.SubElement(s_tag, 'nports').text = str(int(iosig[inout]['max_ports']) -
                                                                  len(iosig[inout]['type'])+1)
        if self.doc is not None:
            ET.SubElement(root, 'doc').text = self.doc
        self.root = root

    def save(self, filename):
        """ Write the XML file """
        self.make_xml()
        open(filename, 'w').write(self._prettyprint())

### Remove module ###########################################################
class ModToolMakeXML(ModTool):
    """ Make XML file for GRC block bindings """
    name = 'makexml'
    aliases = ('mx',)
    def __init__(self):
        ModTool.__init__(self)

    def setup_parser(self):
        " Initialise the option parser for 'gr_modtool.py makexml' "
        parser = ModTool.setup_parser(self)
        parser.usage = '%prog makexml [options]. \n Call %prog without any options to run it interactively.'
        ogroup = OptionGroup(parser, "Make XML module options")
        ogroup.add_option("-p", "--pattern", type="string", default=None,
                help="Filter possible choices for blocks to be parsed.")
        ogroup.add_option("-y", "--yes", action="store_true", default=False,
                help="Answer all questions with 'yes'. This can overwrite existing files!")
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
            self._info['pattern'] = raw_input('Which blocks do you want to parse? (Regex): ')
        if len(self._info['pattern']) == 0:
            self._info['pattern'] = '.'
        self._info['yes'] = options.yes

    def run(self):
        """ Go, go, go! """
        print "Warning: This is an experimental feature. Don't expect any magic."
        # 1) Go through lib/
        if not self._skip_subdirs['lib']:
            files = self._search_files('lib', '*.cc')
            for f in files:
                if os.path.basename(f)[0:2] == 'qa':
                    continue
                (params, iosig, blockname) = self._parse_cc_h(f)
                self._make_grc_xml_from_block_data(params, iosig, blockname)
        # 2) Go through python/


    def _search_files(self, path, path_glob):
        """ Search for files matching pattern in the given path. """
        files = glob.glob("%s/%s"% (path, path_glob))
        files_filt = []
        print "Searching for matching files in %s/:" % path
        for f in files:
            if re.search(self._info['pattern'], os.path.basename(f)) is not None:
                files_filt.append(f)
        if len(files_filt) == 0:
            print "None found."
        return files_filt

    def _make_grc_xml_from_block_data(self, params, iosig, blockname):
        """ Take the return values from the parser and call the XML
        generator. Also, check the makefile if the .xml file is in there.
        If necessary, add. """
        fname_xml = '%s_%s.xml' % (self._info['modname'], blockname)
        # Some adaptions for the GRC
        for inout in ('in', 'out'):
            if iosig[inout]['max_ports'] == '-1':
                iosig[inout]['max_ports'] = '$num_%sputs' % inout
                params.append({'key': 'num_%sputs' % inout,
                               'type': 'int',
                               'name': 'Num %sputs' % inout,
                               'default': '2',
                               'in_constructor': False})
        if os.path.isfile(os.path.join('grc', fname_xml)):
            # TODO add an option to keep
            print "Warning: Overwriting existing GRC file."
        grc_generator = GRCXMLGenerator(
                modname=self._info['modname'],
                blockname=blockname,
                params=params,
                iosig=iosig
        )
        grc_generator.save(os.path.join('grc', fname_xml))
        if not self._skip_subdirs['grc']:
            ed = CMakeFileEditor(self._file['cmgrc'])
            if re.search(fname_xml, ed.cfile) is None:
                print "Adding GRC bindings to grc/CMakeLists.txt..."
                ed.append_value('install', fname_xml, 'DESTINATION[^()]+')
                ed.write()


    def _parse_cc_h(self, fname_cc):
        """ Go through a .cc and .h-file defining a block and return info """
        def _type_translate(p_type, default_v=None):
            """ Translates a type from C++ to GRC """
            translate_dict = {'float': 'real',
                              'double': 'real',
                              'gr_complex': 'complex',
                              'char': 'byte',
                              'unsigned char': 'byte'}
            if default_v is not None and default_v[0:2] == '0x' and p_type == 'int':
                return 'hex'
            if p_type in translate_dict.keys():
                return translate_dict[p_type]
            return p_type
        def _get_blockdata(fname_cc):
            """ Return the block name and the header file name from the .cc file name """
            blockname = os.path.splitext(os.path.basename(fname_cc))[0]
            fname_h = blockname + '.h'
            blockname = blockname.replace(self._info['modname']+'_', '', 1) # Deprecate 3.7
            return (blockname, fname_h)
        # Go, go, go
        print "Making GRC bindings for %s..." % fname_cc
        (blockname, fname_h) = _get_blockdata(fname_cc)
        try:
            parser = ParserCCBlock(fname_cc,
                                   os.path.join('include', fname_h),
                                   blockname, _type_translate
                                  )
        except IOError:
            print "Can't open some of the files necessary to parse %s." % fname_cc
            sys.exit(1)
        return (parser.read_params(), parser.read_io_signature(), blockname)


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
        print "Using Python < 2.7 possibly buggy. Ahem. Please send all complaints to /dev/null."
    main()

