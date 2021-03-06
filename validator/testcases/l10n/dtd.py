
from validator.contextgenerator import ContextGenerator

try:
    from HTMLParser import HTMLParser
except ImportError: # pragma: no cover
    from html.parser import HTMLParser


class DTDParser(object):
    "Parses and serializes DTD files. This is useful for L10n tests."
    
    def __init__(self, dtd):
        """
        Creation of DTD parsers can be done based on a local file
        (provided as a string to the path), or directly (in memory as a
        StringIO object).
        """
        
        self.entities = {}
        self.items = []
        
        if isinstance(dtd, str):
            dtd_instance = open(dtd)
            data = dtd_instance.read()
            dtd_instance.close()
        else:
            data = dtd.getvalue()
        
        self._parse(data)

        # Create a context for the file
        self.context = ContextGenerator(data)
    
    def __len__(self):
        return len(self.entities)
    
    def _parse(self, data):
        "Parses the DTD data and stores it in an aggregate format."
        
        split = data.split("\n")
        parser = DTDXMLParser()
        # Feed the DTD file in line-by-line.
        for line in split:
            line += "\n"
            try:
                parser.feed(line)
            except:
                parser = DTDXMLParser()
            else:
                if parser.out_buffer:
                    for name, value, line in parser.out_buffer:
                        self.entities[name] = value
                        self.items.append((name, value, line))
                    parser.clear_buffer()
        

class DTDXMLParser(HTMLParser):
    "Parses the individual XML entities in a DTD document."
    
    def __init__(self):
        HTMLParser.__init__(self)
        self.out_buffer = []
        
    def unknown_decl(self, decl):
        "Handles non-DOCTYPE SGML declarations in *ML documents."
        
        decl = decl.strip()
        split_decl = decl.split()
        
        if not split_decl[0] == "ENTITY" or len(split_decl) < 3:
            # Interestingly enough, it legitimately IS an unknown
            # declaration. Funny thing, you know?
            # TODO: Log an error?
            return
        
        self.out_buffer.append((split_decl[1],
                                split_decl[2].strip('\'"'),
                                self.getpos()[0])) # Pos 0 is the line #
        
    def clear_buffer(self):
        "Clears the return buffer."
        self.out_buffer = []
        

