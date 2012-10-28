""" A code generator (needed by ModToolAdd) """

import re
from templates import Templates
import Cheetah.Template

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
