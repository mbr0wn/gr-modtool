#!/usr/bin/env python
""" A tool for editing GNU Radio out-of-tree modules. """

import sys
from templates import Templates
from modtool_base import ModTool
from modtool_help import ModToolHelp
from modtool_add import ModToolAdd
from modtool_rm import ModToolRemove
from modtool_newmod import ModToolNewModule
from modtool_makexml import ModToolMakeXML
from util_functions import get_command_from_argv

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
        print "Python 2.6 possibly buggy. Ahem."
    main()

