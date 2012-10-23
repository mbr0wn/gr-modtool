import xml.etree.ElementTree as ET
try:
    import lxml.etree
    LXML_IMPORTED = True
except ImportError:
    LXML_IMPORTED = False

#from xml.etree import ElementTree
#def indent(elem, level=0):
    #i = "\n" + level*"  "
    #if len(elem):
        #if not elem.text or not elem.text.strip():
            #elem.text = i + "  "
        #if not elem.tail or not elem.tail.strip():
            #elem.tail = i
        #for elem in elem:
            #indent(elem, level+1)
        #if not elem.tail or not elem.tail.strip():
            #elem.tail = i
    #else:
        #if level and (not elem.tail or not elem.tail.strip()):
            #elem.tail = i

#root = ElementTree.parse('/tmp/xmlfile').getroot()
#indent(root)

from util_functions import is_number

class GRCXMLGenerator(object):
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

    def make_xml(self):
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
            ET.SubElement(param_tag, 'value').text = param['default']
        for inout in iosig.keys():
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
        #tree = ET.ElementTree(root)
        self.root = root

    def save(self, filename):
        """docstring for save"""
        self.make_xml()
        #print ET.tostring(self.root, encoding="UTF-8")
        #self.tree.write(filename, encoding="UTF-8", xml_declaration=True)
        open(filename, 'w').write(
                lxml.etree.tostring(
                    lxml.etree.fromstring(ET.tostring(self.root, encoding="UTF-8")),
                    pretty_print=True
                )
        )



if __name__ == "__main__":
    data = {'name': 'FooBar',
            'key': 'howto_foo_ff',
            'category': 'HOWTO',
            'import': 'import howto',
            'make': 'howto.foo_ff'}
    gen = GRCXMLGenerator(data)
    gen.make_xml()

