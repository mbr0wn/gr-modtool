""" Edit CMakeLists.txt files """

import re

### CMakeFile.txt editor class ###############################################
class CMakeFileEditor(object):
    """A tool for editing CMakeLists.txt files. """
    def __init__(self, filename, separator=' '):
        self.filename = filename
        self.cfile = open(filename, 'r').read()
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
            for word in re.split('[ )(\t\n\r\f\v]', line):
                if fname_re.match(word) and reg.search(word):
                    filenames.append(word)
        return filenames


    def disable_file(self, fname):
        """ Comment out a file """
        # find filename
        # check if @ beginning of line (if not, add \n + indent)
        # check if @ end of line (if not, add \n)
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
            comment_out_re = r'\n\t' + comment_out_re
        if not ends_line:
            comment_out_re = comment_out_re + '\n\t'
        self.cfile = re.sub(r'('+fname+r')\s*', comment_out_re, self.cfile)

    def comment_out_lines(self, pattern):
        """ Comments out all lines that match with pattern """
        for line in self.cfile.splitlines():
            if re.search(pattern, line):
                self.cfile = self.cfile.replace(line, '#'+line)

