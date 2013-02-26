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
    open(filename, 'w').write(pattern.sub('', oldfile))

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
    """ Grep the current module's name from gnuradio.project or CMakeLists.txt """
    modname_trans = {'howto-write-a-block': 'howto'}
    try:
        prfile = open('gnuradio.project', 'r').read()
        regexp = r'projectname\s*=\s*([a-zA-Z0-9-_]+)$'
        return re.search(regexp, prfile, flags=re.MULTILINE).group(1).strip()
    except IOError:
        pass
    # OK, there's no gnuradio.project. So, we need to guess.
    cmfile = open('CMakeLists.txt', 'r').read()
    regexp = r'(project\s*\(\s*|GR_REGISTER_COMPONENT\(")gr-(?P<modname>[a-zA-Z1-9-_]+)(\s*(CXX)?|" ENABLE)'
    try:
        modname = re.search(regexp, cmfile, flags=re.MULTILINE).group('modname').strip()
        if modname in modname_trans.keys():
            modname = modname_trans[modname]
        return modname
    except AttributeError:
        return None

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

def ask_yes_no(question, default):
    """ Asks a binary question. Returns True for yes, False for no.
    default is given as a boolean. """
    question += {True: ' [Y/n] ', False: ' [y/N] '}[default]
    if raw_input(question).lower() != {True: 'n', False: 'y'}[default]:
        return default
    else:
        return not default
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

# Header file of a sync/decimator/interpolator block
Templates['block_impl_h'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}
\#ifndef INCLUDED_${modname.upper()}_${blockname.upper()}_IMPL_H
\#define INCLUDED_${modname.upper()}_${blockname.upper()}_IMPL_H

\#include <${modname}/${blockname}.h>

namespace gr {
  namespace ${modname} {

    class ${blockname}_impl : public ${blockname}
    {
    private:
      // Nothing to declare in this block.

    public:
      ${blockname}_impl(${strip_default_values($arglist)});
      ~${blockname}_impl();

#if $blocktype == 'general'
      void forecast (int noutput_items, gr_vector_int &ninput_items_required);

      // Where all the action really happens
      int general_work(int noutput_items,
		       gr_vector_int &ninput_items,
		       gr_vector_const_void_star &input_items,
		       gr_vector_void_star &output_items);
#else if $blocktype == 'hier'
#silent pass
#else
      // Where all the action really happens
      int work(int noutput_items,
	       gr_vector_const_void_star &input_items,
	       gr_vector_void_star &output_items);
#end if
    };

  } // namespace ${modname}
} // namespace gr

\#endif /* INCLUDED_${modname.upper()}_${blockname.upper()}_IMPL_H */

'''

# C++ file of a GR block
Templates['block_impl_cpp'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}
\#ifdef HAVE_CONFIG_H
\#include "config.h"
\#endif

\#include <gr_io_signature.h>
#if $blocktype == 'noblock'
\#include <${modname}/${blockname}.h>
#else
\#include "${blockname}_impl.h"
#end if

namespace gr {
  namespace ${modname} {

#if $blocktype == 'noblock'
    $blockname::${blockname}(${strip_default_values($arglist)})
    {
    }

    $blockname::~${blockname}()
    {
    }
#else
    ${blockname}::sptr
    ${blockname}::make(${strip_default_values($arglist)})
    {
      return gnuradio::get_initial_sptr (new ${blockname}_impl(${strip_arg_types($arglist)}));
    }

#if $blocktype == 'decimator'
#set $decimation = ', <+decimation+>'
#else if $blocktype == 'interpolator'
#set $decimation = ', <+interpolation+>'
#else
#set $decimation = ''
#end if
#if $blocktype == 'source'
#set $inputsig = '0, 0, 0'
#else
#set $inputsig = '<+MIN_IN+>, <+MAX_IN+>, sizeof (<+float+>)'
#end if
#if $blocktype == 'sink'
#set $outputsig = '0, 0, 0'
#else
#set $outputsig = '<+MIN_IN+>, <+MAX_IN+>, sizeof (<+float+>)'
#end if
    /*
     * The private constructor
     */
    ${blockname}_impl::${blockname}_impl(${strip_default_values($arglist)})
      : ${grblocktype}("${blockname}",
		      gr_make_io_signature($inputsig),
		      gr_make_io_signature($outputsig)$decimation)
#if $blocktype == 'hier'
    {
        connect(self(), 0, d_firstblock, 0);
        // connect other blocks
        connect(d_lastblock, 0, self(), 0);
    }
#else
    {}
#end if

    /*
     * Our virtual destructor.
     */
    ${blockname}_impl::~${blockname}_impl()
    {
    }

#if $blocktype == 'general'
    void
    ${blockname}_impl::forecast (int noutput_items, gr_vector_int &ninput_items_required)
    {
        /* <+forecast+> e.g. ninput_items_required[0] = noutput_items */
    }

    int
    ${blockname}_impl::general_work (int noutput_items,
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
#else if $blocktype == 'hier'
#silent pass
#else
    int
    ${blockname}_impl::work(int noutput_items,
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
#end if

  } /* namespace ${modname} */
} /* namespace gr */

'''

# Block definition header file (for include/)
Templates['block_def_h'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}

\#ifndef INCLUDED_${modname.upper()}_${blockname.upper()}_H
\#define INCLUDED_${modname.upper()}_${blockname.upper()}_H

\#include <${modname}/api.h>
\#include <${grblocktype}.h>

namespace gr {
  namespace ${modname} {

#if $blocktype == 'noblock'
    /*!
     * \\brief <+description+>
     *
     */
    class ${modname.upper()}_API $blockname
    {
        ${blockname}(${arglist});
        ~${blockname}();
        private:
    };
#else
    /*!
     * \\brief <+description of block+>
     * \ingroup ${modname}
     *
     */
    class ${modname.upper()}_API ${blockname} : virtual public $grblocktype
    {
    public:
       typedef boost::shared_ptr<${blockname}> sptr;

       /*!
        * \\brief Return a shared_ptr to a new instance of ${modname}::${blockname}.
        *
        * To avoid accidental use of raw pointers, ${modname}::${blockname}'s
        * constructor is in a private implementation
        * class. ${modname}::${blockname}::make is the public interface for
        * creating new instances.
        */
       static sptr make($arglist);
    };
#end if

  } // namespace ${modname}
} // namespace gr

\#endif /* INCLUDED_${modname.upper()}_${blockname.upper()}_H */

'''

# Python block (from grextras!)
Templates['block_python'] = '''\#!/usr/bin/env python
${str_to_python_comment($license)}
#
#if $blocktype == 'noblock'
#stop
#end if

#if $blocktype in ('sync', 'sink', 'source')
#set $parenttype = 'gr.sync_block'
#else
#set $parenttype = {'hier': 'gr.hier_block2', 'interpolator': 'gr.interp_block', 'decimator': 'gr.decim_block', 'general': 'gr.block'}[$blocktype]
#end if
#if $blocktype != 'hier'
import numpy
#if $blocktype == 'source'
#set $inputsig = 'None'
#else
#set $inputsig = '[<+numpy.float+>]'
#end if
#if $blocktype == 'sink'
#set $outputsig = 'None'
#else
#set $outputsig = '[<+numpy.float+>]'
#end if
#else
#if $blocktype == 'source'
#set $inputsig = '0, 0, 0'
#else
#set $inputsig = '<+MIN_IN+>, <+MAX_IN+>, gr.sizeof_<+float+>'
#end if
#if $blocktype == 'sink'
#set $outputsig = '0, 0, 0'
#else
#set $outputsig = '<+MIN_OUT+>, <+MAX_OUT+>, gr.sizeof_<+float+>'
#end if
#end if
#if $blocktype == 'interpolator'
#set $deciminterp = ', <+interpolation+>'
#else if $blocktype == 'decimator'
#set $deciminterp = ', <+decimation+>'
#else
#set $deciminterp = ''
#end if
from gnuradio import gr

class ${blockname}(${parenttype}):
    """
    docstring for block ${blockname}
    """
    def __init__(self#if $arglist == '' then '' else ', '#$arglist):
        ${parenttype}.__init__(self,
#if $blocktype == 'hier'
            "$blockname",
            gr.io_signature(${inputsig}),  # Input signature
            gr.io_signature(${outputsig})) # Output signature

            # Define blocks and connect them
            self.connect()
#stop
#else
            name="${blockname}",
            in_sig=${inputsig},
            out_sig=${outputsig}${deciminterp})
#end if

#if $blocktype == 'general'
    def forecast(self, noutput_items, ninput_items_required):
        #setup size of input_items[i] for work call
        for i in range(len(ninput_items_required)):
            ninput_items_required[i] = noutput_items

    def general_work(self, input_items, output_items):
        output_items[0][:] = input_items[0]
        consume(0, len(input_items[0])
        \#self.consume_each(len(input_items[0]))
        return len(output_items[0])
#stop
#end if

    def work(self, input_items, output_items):
#if $blocktype != 'source'
        in0 = input_items[0]
#end if
#if $blocktype != 'sink'
        out = output_items[0]
#end if
        # <+signal processing here+>
#if $blocktype in ('sync', 'decimator', 'interpolator')
        out[:] = in0
        return len(output_items[0])
#else if $blocktype == 'sink'
        return len(input_items[0])
#else if $blocktype == 'source'
        out[:] = whatever
        return len(output_items[0])
#end if

'''

# C++ file for QA
Templates['qa_cpp'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}

\#include "qa_${blockname}.h"
\#include <cppunit/TestAssert.h>

\#include <$modname/${blockname}.h>

namespace gr {
  namespace ${modname} {

    void
    qa_${blockname}::t1()
    {
        // Put test here
    }

  } /* namespace ${modname} */
} /* namespace gr */

'''

# Header file for QA
Templates['qa_h'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}

\#ifndef _QA_${blockname.upper()}_H_
\#define _QA_${blockname.upper()}_H_

\#include <cppunit/extensions/HelperMacros.h>
\#include <cppunit/TestCase.h>

namespace gr {
  namespace ${modname} {

    class qa_${blockname} : public CppUnit::TestCase
    {
    public:
      CPPUNIT_TEST_SUITE(qa_${blockname});
      CPPUNIT_TEST(t1);
      CPPUNIT_TEST_SUITE_END();

    private:
      void t1();
    };

  } /* namespace ${modname} */
} /* namespace gr */

\#endif /* _QA_${blockname.upper()}_H_ */

'''

# Python QA code
Templates['qa_python'] = '''\#!/usr/bin/env python
${str_to_python_comment($license)}
#

from gnuradio import gr, gr_unittest
#if $lang == 'cpp'
import ${modname}_swig as ${modname}
#else
from ${blockname} import ${blockname}
#end if

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

# Usage
Templates['usage'] = '''
gr_modtool <command> [options] -- Run <command> with the given options.
gr_modtool help -- Show a list of commands.
gr_modtool help <command> -- Shows the help for a given command. '''

# SWIG string
Templates['swig_block_magic'] = """#if $version == '36'
GR_SWIG_BLOCK_MAGIC($modname, $blockname);
%include "${modname}_${blockname}.h"
#else
%include "${modname}/${blockname}.h"
GR_SWIG_BLOCK_MAGIC2($modname, $blockname);
#end if
"""

## Old stuff
# C++ file of a GR block
Templates['block_cpp36'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}
\#ifdef HAVE_CONFIG_H
\#include "config.h"
\#endif

#if $blocktype != 'noblock'
\#include <gr_io_signature.h>
#end if
\#include "${modname}_${blockname}.h"

#if $blocktype == 'noblock'
${modname}_${blockname}::${modname}_${blockname}(${strip_default_values($arglist)})
{
}

${modname}_${blockname}::~${modname}_${blockname}()
{
}
#else
${modname}_${blockname}_sptr
${modname}_make_${blockname} (${strip_default_values($arglist)})
{
	return gnuradio::get_initial_sptr (new ${modname}_${blockname}(${strip_arg_types($arglist)}));
}

#if $blocktype == 'decimator'
#set $decimation = ', <+decimation+>'
#else if $blocktype == 'interpolator'
#set $decimation = ', <+interpolation+>'
#else
#set $decimation = ''
#end if
#if $blocktype == 'sink'
#set $inputsig = '0, 0, 0'
#else
#set $inputsig = '<+MIN_IN+>, <+MAX_IN+>, sizeof (<+float+>)'
#end if
#if $blocktype == 'source'
#set $outputsig = '0, 0, 0'
#else
#set $outputsig = '<+MIN_OUT+>, <+MAX_OUT+>, sizeof (<+float+>)'
#end if

/*
 * The private constructor
 */
${modname}_${blockname}::${modname}_${blockname} (${strip_default_values($arglist)})
  : ${grblocktype} ("${blockname}",
		   gr_make_io_signature($inputsig),
		   gr_make_io_signature($outputsig)$decimation)
{
#if $blocktype == 'hier'
		connect(self(), 0, d_firstblock, 0);
		// <+connect other blocks+>
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
#end if


#if $blocktype == 'general'
void
${modname}_${blockname}::forecast (int noutput_items, gr_vector_int &ninput_items_required)
{
	/* <+forecast+> e.g. ninput_items_required[0] = noutput_items */
}

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
#else if $blocktype == 'hier' or $blocktype == 'noblock'
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
Templates['block_h36'] = '''/* -*- c++ -*- */
${str_to_fancyc_comment($license)}

\#ifndef INCLUDED_${modname.upper()}_${blockname.upper()}_H
\#define INCLUDED_${modname.upper()}_${blockname.upper()}_H

\#include <${modname}_api.h>
#if $blocktype == 'noblock'
class ${modname.upper()}_API $blockname
{
	${blockname}(${arglist});
	~${blockname}();
 private:
};

#else
\#include <${grblocktype}.h>

class ${modname}_${blockname};

typedef boost::shared_ptr<${modname}_${blockname}> ${modname}_${blockname}_sptr;

${modname.upper()}_API ${modname}_${blockname}_sptr ${modname}_make_${blockname} ($arglist);

/*!
 * \\brief <+description+>
 * \ingroup ${modname}
 *
 */
class ${modname.upper()}_API ${modname}_${blockname} : public $grblocktype
{
 private:
	friend ${modname.upper()}_API ${modname}_${blockname}_sptr ${modname}_make_${blockname} (${strip_default_values($arglist)});

	${modname}_${blockname}(${strip_default_values($arglist)});

 public:
  ~${modname}_${blockname}();

#if $blocktype == 'general'
	void forecast (int noutput_items, gr_vector_int &ninput_items_required);

	// Where all the action really happens
	int general_work (int noutput_items,
	    gr_vector_int &ninput_items,
	    gr_vector_const_void_star &input_items,
	    gr_vector_void_star &output_items);
#else if $blocktype == 'hier'
#pass
#else
	// Where all the action really happens
	int work (int noutput_items,
	    gr_vector_const_void_star &input_items,
	    gr_vector_void_star &output_items);
#end if
};
#end if

\#endif /* INCLUDED_${modname.upper()}_${blockname.upper()}_H */

'''

# C++ file for QA
Templates['qa_cpp36'] = '''/* -*- c++ -*- */
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

# Header file for QA
Templates['qa_cmakeentry36'] = """
add_executable($basename $filename)
target_link_libraries($basename gnuradio-$modname \${Boost_LIBRARIES})
GR_ADD_TEST($basename $basename)
"""

### Code generator class #####################################################
class GRMTemplate(Cheetah.Template.Template):
    """ An extended template class """
    def __init__(self, src, searchList):
        self.grtypelist = {
                'sync': 'gr_sync_block',
                'sink': 'gr_sync_block',
                'source': 'gr_sync_block',
                'decimator': 'gr_sync_decimator',
                'interpolator': 'gr_sync_interpolator',
                'general': 'gr_block',
                'hier': 'gr_hier_block2',
                'noblock': ''}
        searchList['str_to_fancyc_comment'] = str_to_fancyc_comment
        searchList['str_to_python_comment'] = str_to_python_comment
        searchList['strip_default_values'] = strip_default_values
        searchList['strip_arg_types'] = strip_arg_types
        Cheetah.Template.Template.__init__(self, src, searchList=searchList)
        self.grblocktype = self.grtypelist[searchList['blocktype']]

def get_template(tpl_id, **kwargs):
    """ Return the template given by tpl_id, parsed through Cheetah """
    return str(GRMTemplate(Templates[tpl_id], searchList=kwargs))
### CMakeFile.txt editor class ###############################################
class CMakeFileEditor(object):
    """A tool for editing CMakeLists.txt files. """
    def __init__(self, filename, separator='\n    ', indent='    '):
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
            if len(line.strip()) == 0 or line.strip()[0] == '#':
                continue
            for word in re.split('[ /)(\t\n\r\f\v]', line):
                if fname_re.match(word) and reg.search(word):
                    filenames.append(word)
        return filenames

    def disable_file(self, fname):
        """ Comment out a file """
        starts_line = False
        for line in self.cfile.splitlines():
            if len(line.strip()) == 0 or line.strip()[0] == '#':
                continue
            if re.search(r'\b'+fname+r'\b', line):
                if re.match(fname, line.lstrip()):
                    starts_line = True
                break
        comment_out_re = r'#\1' + '\n' + self.indent
        if not starts_line:
            comment_out_re = r'\n' + self.indent + comment_out_re
        (self.cfile, nsubs) = re.subn(r'(\b'+fname+r'\b)\s*', comment_out_re, self.cfile)
        if nsubs == 0:
            print "Warning: A replacement failed when commenting out %s. Check the CMakeFile.txt manually." % fname
        elif nsubs > 1:
            print "Warning: Replaced %s %d times (instead of once). Check the CMakeFile.txt manually." % (fname, nsubs)

    def comment_out_lines(self, pattern, comment_str='#'):
        """ Comments out all lines that match with pattern """
        for line in self.cfile.splitlines():
            if re.search(pattern, line):
                self.cfile = self.cfile.replace(line, comment_str+line)

    def check_for_glob(self, globstr):
        """ Returns true if a glob as in globstr is found in the cmake file """
        glob_re = r'GLOB\s[a-z_]+\s"%s"' % globstr.replace('*', '\*')
        if re.search(glob_re, self.cfile, flags=re.MULTILINE|re.IGNORECASE) is not None: 
            return True
        else:
            return False

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
        ogroup.add_option("--skip-grc", action="store_true", default=False,
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
        if options.module_name is not None:
            self._info['modname'] = options.module_name
        else:
            self._info['modname'] = get_modname()
        if self._info['modname'] is None:
            print "No GNU Radio module found in the given directory. Quitting."
            sys.exit(1)
        print "GNU Radio module name identified: " + self._info['modname']
        if self._info['version'] == '36' and os.path.isdir(os.path.join('include', self._info['modname'])):
            self._info['version'] = '37'
        if options.skip_lib or not self._has_subdirs['lib']:
            self._skip_subdirs['lib'] = True
        if options.skip_python or not self._has_subdirs['python']:
            self._skip_subdirs['python'] = True
        if options.skip_swig or self._get_mainswigfile() is None or not self._has_subdirs['swig']:
            self._skip_subdirs['swig'] = True
        if options.skip_grc or not self._has_subdirs['grc']:
            self._skip_subdirs['grc'] = True
        self._info['blockname'] = options.block_name
        self.options = options
        self._setup_files()

    def _setup_files(self):
        """ Initialise the self._file[] dictionary """
        if not self._skip_subdirs['swig']:
            self._file['swig'] = os.path.join('swig',   self._get_mainswigfile())
        self._file['qalib']    = os.path.join('lib',    'qa_%s.cc' % self._info['modname'])
        self._file['pyinit']   = os.path.join('python', '__init__.py')
        self._file['cmlib']    = os.path.join('lib',    'CMakeLists.txt')
        self._file['cmgrc']    = os.path.join('grc',    'CMakeLists.txt')
        self._file['cmpython'] = os.path.join('python', 'CMakeLists.txt')
        if self._info['version'] in ('37', 'component'):
            self._info['includedir'] = os.path.join('include', self._info['modname'])
        else:
            self._info['includedir'] = 'include'
        self._file['cminclude'] = os.path.join(self._info['includedir'], 'CMakeLists.txt')
        self._file['cmswig'] = os.path.join('swig', 'CMakeLists.txt')

    def _check_directory(self, directory):
        """ Guesses if dir is a valid GNU Radio module directory by looking for
        CMakeLists.txt and at least one of the subdirs lib/, python/ and swig/.
        Changes the directory, if valid. """
        has_makefile = False
        try:
            files = os.listdir(directory)
            os.chdir(directory)
        except OSError:
            print "Can't read or chdir to directory %s." % directory
            return False
        for f in files:
            if os.path.isfile(f) and f == 'CMakeLists.txt':
                if re.search('find_package\(GnuradioCore\)', open(f).read()) is not None:
                    self._info['version'] = '36' # Might be 37, check that later
                    has_makefile = True
                elif re.search('GR_REGISTER_COMPONENT', open(f).read()) is not None:
                    self._info['version'] = '36' # Might be 37, check that later
                    self._info['is_component'] = True
                    has_makefile = True
            # TODO search for autofoo
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

    def run(self):
        """ Override this. """
        pass

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
        ogroup.add_option("--suggested-dirs", default=None, type="string",
                help="Suggest typical include dirs if nothing better can be detected.")
        parser.add_option_group(ogroup)
        return parser

    def setup(self):
        # Won't call parent's setup(), because that's too chatty
        (self.options, self.args) = self.parser.parse_args()

    def run(self):
        """ Go, go, go! """
        mod_info = {}
        mod_info['base_dir'] = self._get_base_dir(self.options.directory)
        if mod_info['base_dir'] is None:
            if self.options.python_readable:
                print '{}'
            else:
                print "No module found."
            exit(1)
        os.chdir(mod_info['base_dir'])
        mod_info['modname'] = get_modname()
        if mod_info['modname'] is None:
            if self.options.python_readable:
                print '{}'
            else:
                print "No module found."
            exit(1)
        if self._info['version'] == '36' and os.path.isdir(os.path.join('include', mod_info['modname'])):
            self._info['version'] = '37'
        mod_info['version'] = self._info['version']
        if 'is_component' in self._info.keys():
            mod_info['is_component'] = True
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
        base_build_dir = mod_info['base_dir']
        if 'is_component' in mod_info.keys():
            (base_build_dir, rest_dir) = os.path.split(base_build_dir)
        has_build_dir = os.path.isdir(os.path.join(base_build_dir , 'build'))
        if (has_build_dir and os.path.isfile(os.path.join(base_build_dir, 'CMakeCache.txt'))):
            return os.path.join(base_build_dir, 'build')
        else:
            for (dirpath, dirnames, filenames) in os.walk(base_build_dir):
                if 'CMakeCache.txt' in filenames:
                    return dirpath
        if has_build_dir:
            return os.path.join(base_build_dir, 'build')
        return None

    def _get_include_dirs(self, mod_info):
        """ Figure out include dirs for the make process. """
        inc_dirs = []
        path_or_internal = {True: 'INTERNAL',
                            False: 'PATH'}['is_component' in mod_info.keys()]
        try:
            cmakecache_fid = open(os.path.join(mod_info['build_dir'], 'CMakeCache.txt'))
            for line in cmakecache_fid:
                if line.find('GNURADIO_CORE_INCLUDE_DIRS:%s' % path_or_internal) != -1:
                    inc_dirs += line.replace('GNURADIO_CORE_INCLUDE_DIRS:%s=' % path_or_internal, '').strip().split(';')
                if line.find('GRUEL_INCLUDE_DIRS:%s' % path_or_internal) != -1:
                    inc_dirs += line.replace('GRUEL_INCLUDE_DIRS:%s=' % path_or_internal, '').strip().split(';')
        except IOError:
            pass
        if len(inc_dirs) == 0 and self.options.suggested_dirs is not None:
            inc_dirs = [os.path.normpath(path) for path in self.options.suggested_dirs.split(':') if os.path.isdir(path)]
        return inc_dirs

    def _pretty_print(self, mod_info):
        """ Output the module info in human-readable format """
        index_names = {'base_dir': 'Base directory',
                       'modname':  'Module name',
                       'is_component':  'Is GR component',
                       'build_dir': 'Build directory',
                       'incdirs': 'Include directories'}
        for key in mod_info.keys():
            if key == 'version':
                print "        API version: %s" % {
                        '36': 'pre-3.7',
                        '37': 'post-3.7',
                        'autofoo': 'Autotools (pre-3.5)'
                        }[mod_info['version']]
            else:
                print '%19s: %s' % (index_names[key], mod_info[key])

### Add new block module #####################################################
class ModToolAdd(ModTool):
    """ Add block to the out-of-tree module. """
    name = 'add'
    aliases = ('insert',)
    _block_types = ('sink', 'source', 'sync', 'decimator', 'interpolator',
                    'general', 'hier', 'noblock')
    def __init__(self):
        ModTool.__init__(self)
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
        ogroup.add_option("-l", "--lang", type="choice", choices=('cpp', 'c++', 'python'),
                default='cpp', help="Language (cpp or python)")
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
        self._info['lang'] = options.lang
        if self._info['lang'] == 'c++':
            self._info['lang'] = 'cpp'
        print "Language: %s" % {'cpp': 'C++', 'python': 'Python'}[self._info['lang']]

        if ((self._skip_subdirs['lib'] and self._info['lang'] == 'cpp')
             or (self._skip_subdirs['python'] and self._info['lang'] == 'python')):
            print "Missing or skipping relevant subdir."
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
        self._info['fullblockname'] = self._info['modname'] + '_' + self._info['blockname']
        self._info['license'] = self.setup_choose_license()

        if options.argument_list is not None:
            self._info['arglist'] = options.argument_list
        else:
            self._info['arglist'] = raw_input('Enter valid argument list, including default arguments: ')

        if not (self._info['blocktype'] in ('noblock') or self._skip_subdirs['python']):
            self._add_py_qa = options.add_python_qa
            if self._add_py_qa is None:
                self._add_py_qa = ask_yes_no('Add Python QA code?', True)
        if self._info['lang'] == 'cpp':
            self._add_cc_qa = options.add_cpp_qa
            if self._add_cc_qa is None:
                self._add_cc_qa = ask_yes_no('Add C++ QA code?', not self._add_py_qa)
        if self._info['version'] == 'autofoo' and not self.options.skip_cmakefiles:
            print "Warning: Autotools modules are not supported. ",
            print "Files will be created, but Makefiles will not be edited."
            self.options.skip_cmakefiles = True


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
        has_swig = (
                self._info['lang'] == 'cpp'
                and not self._skip_subdirs['swig']
        )
        has_grc = False
        if self._info['lang'] == 'cpp':
            print "Traversing lib..."
            self._run_lib()
            has_grc = has_swig
        else: # Python
            print "Traversing python..."
            self._run_python()
            if self._info['blocktype'] != 'noblock':
                has_grc = True
        if has_swig:
            print "Traversing swig..."
            self._run_swig()
        if self._add_py_qa:
            print "Adding Python QA..."
            self._run_python_qa()
        if has_grc and not self._skip_subdirs['grc']:
            print "Traversing grc..."
            self._run_grc()

    def _run_lib(self):
        """ Do everything that needs doing in the subdir 'lib' and 'include'.
        - add .cc and .h files
        - include them into CMakeLists.txt
        - check if C++ QA code is req'd
        - if yes, create qa_*.{cc,h} and add them to CMakeLists.txt
        """
        def _add_qa():
            " Add C++ QA files for 3.7 API "
            fname_qa_h  = 'qa_%s.h'  % self._info['blockname']
            fname_qa_cc = 'qa_%s.cc' % self._info['blockname']
            self._write_tpl('qa_cpp', 'lib', fname_qa_cc)
            self._write_tpl('qa_h',   'lib', fname_qa_h)
            if not self.options.skip_cmakefiles:
                try:
                    append_re_line_sequence(self._file['cmlib'],
                                            '\$\{CMAKE_CURRENT_SOURCE_DIR\}/qa_%s.cc.*\n' % self._info['modname'],
                                            '  ${CMAKE_CURRENT_SOURCE_DIR}/qa_%s.cc' % self._info['blockname'])
                    append_re_line_sequence(self._file['qalib'],
                                            '#include.*\n',
                                            '#include "%s"' % fname_qa_h)
                    append_re_line_sequence(self._file['qalib'],
                                            '(addTest.*suite.*\n|new CppUnit.*TestSuite.*\n)',
                                            '  s->addTest(gr::%s::qa_%s::suite());' % (self._info['modname'],
                                                                                       self._info['blockname'])
                                            )
                except IOError:
                    print "Can't add C++ QA files."
        def _add_qa36():
            " Add C++ QA files for pre-3.7 API (not autotools) "
            fname_qa_cc = 'qa_%s.cc' % self._info['fullblockname']
            self._write_tpl('qa_cpp36', 'lib', fname_qa_cc)
            if not self.options.skip_cmakefiles:
                open(self._file['cmlib'], 'a').write(
                        str(
                            Cheetah.Template.Template(
                                Templates['qa_cmakeentry36'],
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
        fname_cc = None
        fname_h  = None
        if self._info['version']  == '37':
            fname_h  = self._info['blockname'] + '.h'
            fname_cc = self._info['blockname'] + '.cc'
            if self._info['blocktype'] in ('source', 'sink', 'sync', 'decimator',
                                           'interpolator', 'general', 'hier'):
                fname_cc = self._info['blockname'] + '_impl.cc'
                self._write_tpl('block_impl_h',   'lib', self._info['blockname'] + '_impl.h')
            self._write_tpl('block_impl_cpp', 'lib', fname_cc)
            self._write_tpl('block_def_h',    self._info['includedir'], fname_h)
        else: # Pre-3.7 or autotools
            fname_h  = self._info['fullblockname'] + '.h'
            fname_cc = self._info['fullblockname'] + '.cc'
            self._write_tpl('block_h36',   self._info['includedir'], fname_h)
            self._write_tpl('block_cpp36', 'lib',                    fname_cc)
        if not self.options.skip_cmakefiles:
            ed = CMakeFileEditor(self._file['cmlib'])
            ed.append_value('add_library', fname_cc)
            ed.write()
            ed = CMakeFileEditor(self._file['cminclude'])
            ed.append_value('install', fname_h, 'DESTINATION[^()]+')
            ed.write()
        if self._add_cc_qa:
            if self._info['version'] == '37':
                _add_qa()
            elif self._info['version'] == '36':
                _add_qa36()
            elif self._info['version'] == 'autofoo':
                print "Warning: C++ QA files not supported for autotools."

    def _run_swig(self):
        """ Do everything that needs doing in the subdir 'swig'.
        - Edit main *.i file
        """
        if self._get_mainswigfile() is None:
            print 'Warning: No main swig file found.'
            return
        print "Editing %s..." % self._file['swig']
        mod_block_sep = '/'
        if self._info['version'] == '36':
            mod_block_sep = '_'
        swig_block_magic_str = get_template('swig_block_magic', **self._info)
        open(self._file['swig'], 'a').write(swig_block_magic_str)
        include_str = '#include "%s%s%s.h"' % (
                self._info['modname'],
                mod_block_sep,
                self._info['blockname'])
        if re.search('#include', open(self._file['swig'], 'r').read()):
            append_re_line_sequence(self._file['swig'], '^#include.*\n', include_str)
        else: # I.e., if the swig file is empty
            oldfile = open(self._file['swig'], 'r').read()
            regexp = re.compile('^%\{\n', re.MULTILINE)
            oldfile = regexp.sub('%%{\n%s\n' % include_str, oldfile, count=1)
            open(self._file['swig'], 'w').write(oldfile)

    def _run_python_qa(self):
        """ Do everything that needs doing in the subdir 'python' to add
        QA code.
        - add .py files
        - include in CMakeLists.txt
        """
        fname_py_qa = 'qa_' + self._info['blockname'] + '.py'
        self._write_tpl('qa_python', 'python', fname_py_qa)
        os.chmod(os.path.join('python', fname_py_qa), 0755)
        if self.options.skip_cmakefiles or CMakeFileEditor(self._file['cmpython']).check_for_glob('qa_*.py'):
            return
        print "Editing python/CMakeLists.txt..."
        open(self._file['cmpython'], 'a').write(
                'GR_ADD_TEST(qa_%s ${PYTHON_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/%s)\n' % \
                  (self._info['blockname'], fname_py_qa))

    def _run_python(self):
        """ Do everything that needs doing in the subdir 'python' to add
        a Python block.
        - add .py file
        - include in CMakeLists.txt
        - include in __init__.py
        """
        fname_py = self._info['blockname'] + '.py'
        self._write_tpl('block_python', 'python', fname_py)
        append_re_line_sequence(self._file['pyinit'],
                                '(^from.*import.*\n|# import any pure.*\n)',
                                'from %s import %s' % (self._info['blockname'], self._info['blockname']))
        if self.options.skip_cmakefiles:
            return
        ed = CMakeFileEditor(self._file['cmpython'])
        ed.append_value('GR_PYTHON_INSTALL', fname_py, 'DESTINATION[^()]+')
        ed.write()

    def _run_grc(self):
        """ Do everything that needs doing in the subdir 'grc' to add
        a GRC bindings XML file.
        - add .xml file
        - include in CMakeLists.txt
        """
        fname_grc = self._info['fullblockname'] + '.xml'
        self._write_tpl('grc_xml', 'grc', fname_grc)
        ed = CMakeFileEditor(self._file['cmgrc'], '\n    ')
        if self.options.skip_cmakefiles or ed.check_for_glob('*.xml'):
            return
        print "Editing grc/CMakeLists.txt..."
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
            if self._info['version'] == '37':
                (base, ext) = os.path.splitext(filename)
                if ext == '.h':
                    remove_pattern_from_file(self._file['qalib'],
                                             '^#include "%s"\s*$' % filename)
                    remove_pattern_from_file(self._file['qalib'],
                                             '^\s*s->addTest\(gr::%s::%s::suite\(\)\);\s*$' % (
                                                    self._info['modname'], base)
                                            )
                elif ext == '.cc':
                    ed.remove_value('list',
                                    '\$\{CMAKE_CURRENT_SOURCE_DIR\}/%s' % filename,
                                    'APPEND test_%s_sources' % self._info['modname'])
            else:
                filebase = os.path.splitext(filename)[0]
                ed.delete_entry('add_executable', filebase)
                ed.delete_entry('target_link_libraries', filebase)
                ed.delete_entry('GR_ADD_TEST', filebase)
                ed.remove_double_newlines()

        def _remove_py_test_case(filename=None, ed=None):
            """ Special function that removes the occurrences of a qa*.{cc,h} file
            from the CMakeLists.txt and the qa_$modname.cc. """
            if filename[:2] != 'qa':
                return
            filebase = os.path.splitext(filename)[0]
            ed.delete_entry('GR_ADD_TEST', filebase)
            ed.remove_double_newlines()

        def _make_swig_regex(filename):
            filebase = os.path.splitext(filename)[0]
            pyblockname = filebase.replace(self._info['modname'] + '_', '')
            regexp = r'(^\s*GR_SWIG_BLOCK_MAGIC2?\(%s,\s*%s\);|^\s*.include\s*"(%s/)?%s"\s*)' % \
                    (self._info['modname'], pyblockname, self._info['modname'], filename)
            return regexp
        # Go, go, go!
        if not self._skip_subdirs['lib']:
            self._run_subdir('lib', ('*.cc', '*.h'), ('add_library',),
                             cmakeedit_func=_remove_cc_test_case)
        if not self._skip_subdirs['include']:
            incl_files_deleted = self._run_subdir(self._info['includedir'], ('*.h',), ('install',))
        if not self._skip_subdirs['swig']:
            swig_files_deleted = self._run_subdir('swig', ('*.i',), ('install',))
            for f in incl_files_deleted + swig_files_deleted:
                # TODO do this on all *.i files
                remove_pattern_from_file(self._file['swig'], _make_swig_regex(f))
        if not self._skip_subdirs['python']:
            py_files_deleted = self._run_subdir('python', ('*.py',), ('GR_PYTHON_INSTALL',),
                                                cmakeedit_func=_remove_py_test_case)
            for f in py_files_deleted:
                remove_pattern_from_file(self._file['pyinit'], '.*import\s+%s.*' % f[:-3])
                remove_pattern_from_file(self._file['pyinit'], '.*from\s+%s\s+import.*\n' % f[:-3])
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
                print "Could not edit __init__.py, that might be a problem."
                return False
            pymodname = os.path.splitext(fname)[0]
            initfile = re.sub(r'((from|import)\s+\b'+pymodname+r'\b)', r'#\1', initfile)
            open(self._file['pyinit'], 'w').write(initfile)
            return False
        def _handle_cc_qa(cmake, fname):
            """ Do stuff for cc qa """
            if self._info['version'] == '37':
                cmake.comment_out_lines('\$\{CMAKE_CURRENT_SOURCE_DIR\}/'+fname)
                fname_base = os.path.splitext(fname)[0]
                ed = CMakeFileEditor(self._file['qalib']) # Abusing the CMakeFileEditor...
                ed.comment_out_lines('#include\s+"%s.h"' % fname_base, comment_str='//')
                ed.comment_out_lines('%s::suite\(\)' % fname_base, comment_str='//')
                ed.write()
            elif self._info['version'] == '36':
                cmake.comment_out_lines('add_executable.*'+fname)
                cmake.comment_out_lines('target_link_libraries.*'+os.path.splitext(fname)[0])
                cmake.comment_out_lines('GR_ADD_TEST.*'+os.path.splitext(fname)[0])
            return True
        def _handle_h_swig(cmake, fname):
            """ Comment out include files from the SWIG file,
            as well as the block magic """
            swigfile = open(self._file['swig']).read()
            (swigfile, nsubs) = re.subn('(.include\s+"(%s/)?%s")' % (
                                        self._info['modname'], fname),
                                        r'//\1', swigfile)
            if nsubs > 0:
                print "Changing %s..." % self._file['swig']
            if nsubs > 1: # Need to find a single BLOCK_MAGIC
                blockname = os.path.splitext(fname[len(self._info['modname'])+1:])[0]
                if self._info['version'] == '37':
                    blockname = os.path.splitext(fname)[0]
                (swigfile, nsubs) = re.subn('(GR_SWIG_BLOCK_MAGIC2?.+%s.+;)' % blockname, r'//\1', swigfile)
                if nsubs > 1:
                    print "Hm, changed more then expected while editing %s." % self._file['swig']
            open(self._file['swig'], 'w').write(swigfile)
            return False
        def _handle_i_swig(cmake, fname):
            """ Comment out include files from the SWIG file,
            as well as the block magic """
            swigfile = open(self._file['swig']).read()
            blockname = os.path.splitext(fname[len(self._info['modname'])+1:])[0]
            if self._info['version'] == '37':
                blockname = os.path.splitext(fname)[0]
            swigfile = re.sub('(%include\s+"'+fname+'")', r'//\1', swigfile)
            print "Changing %s..." % self._file['swig']
            swigfile = re.sub('(GR_SWIG_BLOCK_MAGIC2?.+'+blockname+'.+;)', r'//\1', swigfile)
            open(self._file['swig'], 'w').write(swigfile)
            return False
        # List of special rules: 0: subdir, 1: filename re match, 2: function
        special_treatments = (
                ('python', 'qa.+py$', _handle_py_qa),
                ('python', '^(?!qa).+py$', _handle_py_mod),
                ('lib', 'qa.+\.cc$', _handle_cc_qa),
                ('include/%s' % self._info['modname'], '.+\.h$', _handle_h_swig),
                ('include', '.+\.h$', _handle_h_swig),
                ('swig', '.+\.i$', _handle_i_swig)
        )
        for subdir in self._subdirs:
            if self._skip_subdirs[subdir]: continue
            if self._info['version'] == '37' and subdir == 'include':
                subdir = 'include/%s' % self._info['modname']
            try:
                cmake = CMakeFileEditor(os.path.join(subdir, 'CMakeLists.txt'))
            except IOError:
                continue
            print "Traversing %s..." % subdir
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
        print "Careful: 'gr_modtool disable' does not resolve dependencies."

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
        parser.usage = '%prog rm [options]. \n Call %prog without any options to run it interactively.'
        ogroup = OptionGroup(parser, "New out-of-tree module options")
        parser.add_option_group(ogroup)
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
        """
        * Unpack the tar.bz2 to the new locations
        * Remove the bz2
        * Open all files, rename howto and HOWTO to the module name
        * Rename files and directories that contain the word howto
        """
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
        for root, dirs, files in os.walk('.'):
            for filename in files:
                f = os.path.join(root, filename)
                s = open(f, 'r').read()
                s = s.replace('howto', self._info['modname'])
                s = s.replace('HOWTO', self._info['modname'].upper())
                open(f, 'w').write(s)
                if filename.find('howto') != -1:
                    os.rename(f, os.path.join(root, filename.replace('howto', self._info['modname'])))
            if os.path.basename(root) == 'howto':
                os.rename(root, os.path.join(os.path.dirname(root), self._info['modname']))
        print "Done."
        print "Use 'gr_modtool add' to add a new block to this currently empty module."


### CC block parser ##########################################################
def dummy_translator(the_type, default_v=None):
    """ Doesn't really translate. """
    return the_type

class ParserCCBlock(object):
    """ Class to read blocks written in C++ """
    def __init__(self, filename_cc, filename_h, blockname, version, type_trans=dummy_translator):
        self.code_cc = open(filename_cc).read()
        self.code_h  = open(filename_h).read()
        self.blockname = blockname
        self.type_trans = type_trans
        self.version = version

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
        def _scan_param_list(start_idx):
            """ Go through a parameter list and return a tuple each:
                (type, name, default_value). Python's re just doesn't cut
                it for C++ code :( """
            i = start_idx
            c = self.code_h
            if c[i] != '(':
                raise ValueError
            i += 1

            param_list = []
            read_state = 'type'
            in_string = False
            parens_count = 0 # Counts ()
            brackets_count = 0 # Counts <>
            end_of_list = False
            this_type = ''
            this_name = ''
            this_defv = ''
            WHITESPACE = ' \t\n\r\f\v'
            while not end_of_list:
                # Keep track of (), stop when reaching final closing parens
                if not in_string:
                    if c[i] == ')':
                        if parens_count == 0:
                            if read_state == 'type' and len(this_type):
                                raise ValueError(
                                        'Found closing parentheses before finishing last argument (this is how far I got: %s)'
                                        % str(param_list)
                                )
                            if len(this_type):
                                param_list.append((this_type, this_name, this_defv))
                            end_of_list = True
                            break
                        else:
                            parens_count -= 1
                    elif c[i] == '(':
                        parens_count += 1
                # Parameter type (int, const std::string, std::vector<gr_complex>, unsigned long ...)
                if read_state == 'type':
                    if c[i] == '<':
                        brackets_count += 1
                    if c[i] == '>':
                        brackets_count -= 1
                    if c[i] == '&':
                        i += 1
                        continue
                    if c[i] in WHITESPACE and brackets_count == 0:
                        while c[i] in WHITESPACE:
                            i += 1
                            continue
                        if this_type == 'const' or this_type == '': # Ignore this
                            this_type = ''
                        elif this_type == 'unsigned': # Continue
                            this_type += ' '
                            continue
                        else:
                            read_state = 'name'
                        continue
                    this_type += c[i]
                    i += 1
                    continue
                # Parameter name
                if read_state == 'name':
                    if c[i] == '&' or c[i] in WHITESPACE:
                        i += 1
                    elif c[i] == '=':
                        if parens_count != 0:
                            raise ValueError(
                                    'While parsing argument %d (%s): name finished but no closing parentheses.'
                                    % (len(param_list)+1, this_type + ' ' + this_name)
                            )
                        read_state = 'defv'
                        i += 1
                    elif c[i] == ',':
                        if parens_count:
                            raise ValueError(
                                    'While parsing argument %d (%s): name finished but no closing parentheses.'
                                    % (len(param_list)+1, this_type + ' ' + this_name)
                            )
                        read_state = 'defv'
                    else:
                        this_name += c[i]
                        i += 1
                    continue
                # Default value
                if read_state == 'defv':
                    if in_string:
                        if c[i] == '"' and c[i-1] != '\\':
                            in_string = False
                        else:
                            this_defv += c[i]
                    elif c[i] == ',':
                        if parens_count:
                            raise ValueError(
                                    'While parsing argument %d (%s): default value finished but no closing parentheses.'
                                    % (len(param_list)+1, this_type + ' ' + this_name)
                            )
                        read_state = 'type'
                        param_list.append((this_type, this_name, this_defv))
                        this_type = ''
                        this_name = ''
                        this_defv = ''
                    else:
                        this_defv += c[i]
                    i += 1
                    continue
            return param_list
        # Go, go, go!
        if self.version == '37':
            make_regex = 'static\s+sptr\s+make\s*'
        else:
            make_regex = '(?<=_API)\s+\w+_sptr\s+\w+_make_\w+\s*'
        make_match = re.compile(make_regex, re.MULTILINE).search(self.code_h)
        try:
            params_list = _scan_param_list(make_match.end(0))
        except ValueError as ve:
            print "Can't parse the argument list: ", ve.args[0]
            sys.exit(0)
        params = []
        for plist in params_list:
            params.append({'type': self.type_trans(plist[0], plist[2]),
                           'key': plist[1],
                           'default': plist[2],
                           'in_constructor': True})
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
        # Can't make a dict 'cause order matters
        self._header = (('name', blockname.replace('_', ' ').capitalize()),
                        ('key', '%s_%s' % (modname, blockname)),
                        ('category', modname.upper()),
                        ('import', 'import %s' % modname),
                        ('make', '%s.%s(%s)' % (modname, blockname, ', '.join(params_list)))
                       )
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
        for tag, value in self._header:
            this_tag = ET.SubElement(root, tag)
            this_tag.text = value
        for param in self.params:
            param_tag = ET.SubElement(root, 'param')
            ET.SubElement(param_tag, 'name').text = param['key'].capitalize()
            ET.SubElement(param_tag, 'key').text = param['key']
            if len(param['default']):
                ET.SubElement(param_tag, 'value').text = param['default']
            ET.SubElement(param_tag, 'type').text = param['type']
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
            if self._info['version'] == '37':
                files = self._search_files('lib', '*_impl.cc')
            else:
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
            if re.search(fname_xml, ed.cfile) is None and not ed.check_for_glob('*.xml'):
                print "Adding GRC bindings to grc/CMakeLists.txt..."
                ed.append_value('install', fname_xml, 'DESTINATION[^()]+')
                ed.write()

    def _parse_cc_h(self, fname_cc):
        """ Go through a .cc and .h-file defining a block and return info """
        def _type_translate(p_type, default_v=None):
            """ Translates a type from C++ to GRC """
            translate_dict = {'float': 'float',
                              'double': 'real',
                              'int': 'int',
                              'gr_complex': 'complex',
                              'char': 'byte',
                              'unsigned char': 'byte',
                              'std::string': 'string',
                              'std::vector<int>': 'int_vector',
                              'std::vector<float>': 'real_vector',
                              'std::vector<gr_complex>': 'complex_vector',
                              }
            if p_type in ('int',) and default_v[:2].lower() == '0x':
                return 'hex'
            try:
                return translate_dict[p_type]
            except KeyError:
                return 'raw'
        def _get_blockdata(fname_cc):
            """ Return the block name and the header file name from the .cc file name """
            blockname = os.path.splitext(os.path.basename(fname_cc.replace('_impl.', '.')))[0]
            fname_h = (blockname + '.h').replace('_impl.', '.')
            blockname = blockname.replace(self._info['modname']+'_', '', 1)
            return (blockname, fname_h)
        # Go, go, go
        print "Making GRC bindings for %s..." % fname_cc
        (blockname, fname_h) = _get_blockdata(fname_cc)
        try:
            parser = ParserCCBlock(fname_cc,
                                   os.path.join(self._info['includedir'], fname_h),
                                   blockname,
                                   self._info['version'],
                                   _type_translate
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
    try:
        main()
    except KeyboardInterrupt:
        pass

