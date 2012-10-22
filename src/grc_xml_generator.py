import xml.etree.ElementTree as ET
import lxml.etree

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
        for tag in self._header.keys():
            this_tag = ET.SubElement(root, tag)
            this_tag.text = self._header[tag]
        for param in self.params:
            param_tag = ET.SubElement(root, 'param')
            ET.SubElement(param_tag, 'name').text = param['key'].capitalize()
            ET.SubElement(param_tag, 'key').text = param['key']
            ET.SubElement(param_tag, 'type').text = param['type']
            ET.SubElement(param_tag, 'value').text = param['default']
        #if self.iosig['in']['max_ports'] > 0:
            #sink_tag = ET.SubElement(root, 'sink')
            #ET.SubElement(sink_tag, 'name').text('in')
            #ET.SubElement(sink_tag, 'type').text(self.iosig['in']['type'])
            #if self.iosig['in']['vlen'] != '1':
                #ET.SubElement(sink_tag, 'vlen').text(param['vlen']) # FIXME this might trigger another param..?
        #if self.iosig['out']['max_ports'] > 0:
            #sink_tag = ET.SubElement(root, 'source')
            #ET.SubElement(sink_tag, 'name').text('out')
            #ET.SubElement(sink_tag, 'type').text(self.iosig['in']['type'])
            #if self.iosig['in']['vlen'] != '1':
                #ET.SubElement(sink_tag, 'vlen').text(param['vlen']) # FIXME this might trigger another param..?
        #if self.doc is not None or len(self.doc):
            #ET.SubElement(root, 'doc').text(self.doc)
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

