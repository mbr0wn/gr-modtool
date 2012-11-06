''' All the templates for skeleton files (needed by ModToolAdd) '''

from datetime import datetime

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

# Python block (from grextras!)
Templates['block_python'] = '''\#!/usr/bin/env python
${str_to_python_comment($license)}
#

from gnuradio import gr
import gnuradio.extras

#if $blocktype == 'sink'
#set $inputsig = 'None'
#else
#set $inputsig = '[<+numpy.float+>]'
#end if
#if $blocktype == 'source'
#set $outputsig = 'None'
#else
#set $outputsig = '[<+numpy.float+>]'
#end if

class ${blockname}(gr.block):
    def __init__(self, args):
        gr.block.__init__(self, name="${blockname}", in_sig=${inputsig}, out_sig=${outputsig})
#if $blocktype == 'decimator'
        self.set_relative_rate(1.0/<+decimation+>)
#else if $blocktype == 'interpolator'
        self.set_relative_rate(<+interpolation+>)
#else if $blocktype == 'general'
        self.set_auto_consume(False)

    def forecast(self, noutput_items, ninput_items_required):
        #setup size of input_items[i] for work call
        for i in range(len(ninput_items_required)):
            ninput_items_required[i] = noutput_items
#end if

    def work(self, input_items, output_items):
#if $blocktype != 'source'
        in = input_items[0]
#end if
#if $blocktype != 'sink'
        out = output_items[0]
#end if
#if $blocktype in ('sync', 'decimator', 'interpolator')
        # <+signal processing here+>
        out[:] = in
        return len(output_items[0])
#else if $blocktype == 'sink'
        return len(input_items[0])
#else if $blocktype == 'source'
        out[:] = whatever
        return len(output_items[0])
#else if $blocktype == 'general'
        # <+signal processing here+>
        out[:] = in

        self.consume(0, len(in0)) //consume port 0 input
        \#self.consume_each(len(out)) //or shortcut to consume on all inputs

        # return produced
        return len(out)
#end if

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

