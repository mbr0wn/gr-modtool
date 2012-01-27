/* -*- c++ -*- */

#define HOWTO_API

%include "gnuradio.i"			// the common stuff

//load generated python docstrings
%include "howto_swig_doc.i"

%{
%}

#if SWIGGUILE
%scheme %{
(load-extension-global "libguile-gnuradio-howto_swig" "scm_init_gnuradio_howto_swig_module")
%}

%goops %{
(use-modules (gnuradio gnuradio_core_runtime))
%}
#endif
