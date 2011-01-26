import chardet
import codecs

UNICODES = [
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
    (codecs.BOM_UTF8, "utf-8")
    ]

def _decode(data):
    "Decode data employing some character set detection and including unicode BOM stripping"

    # try the unicodes by BOM detection
    # strip the BOM in the process
    for testhead,encoding in UNICODES:
        if data.startswith(testhead):
            return [unicode(data[len(testhead):], encoding, "ignore"), encoding]

    # utf-8 is pretty common (without BOM)
    # includes ascii, which is a subset
    try:
        return [unicode(data, "utf-8"), "utf-8"]
    except UnicodeError:
        pass

    # try chardet detection
    try:
        detected = chardet.detect(data)
        return [unicode(data, detected["encoding"]), detected["encoding"]]
    except:
        pass

    # last resort; try plain unicode without a charset
    return [unicode(data), None]

def decode(data): 
    "Decode data employing some character set detection and including unicode BOM stripping"
    return _decode(data)[0]

def detect(data):
    "Detect encoding of data with a high confidence"
    return _decode(data)[1]
