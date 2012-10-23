''' A parser for blocks written in C++ '''
import re
import sys

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

