from xml.dom.minidom import parse
from validator.constants import *

def detect_type(err, install_rdf=None, xpi_package=None):
    """Determines the type of addon being validated based on
    install.rdf, file extension, and other properties."""
    
    # The types in the install.rdf don't pair up 1:1 with the type
    # system that we're using for expectations and the like. This is
    # to help translate between the two.
    translated_types = {"2": PACKAGE_EXTENSION,
                        "4": PACKAGE_THEME,
                        "8": PACKAGE_LANGPACK,
                        "32": PACKAGE_MULTI}
    
    # If we're missing our install.rdf file, we can try to make some
    # assumptions.
    if install_rdf is None:
        types = {"xpi": PACKAGE_DICTIONARY}
        
        err.info(("typedetection",
                  "detect_type",
                  "missing_install_rdf"),
                 "install.rdf was not found.",
                 """The type should be determined by install.rdf if present.
                 If it isn't, we still need to know the type.""")
        
        # If we know what the file type might be, return it.
        if xpi_package.extension in types:
            return types[xpi_package.extension]
        # Otherwise, we're out of luck :(
        else:
            return None
    
    
    # Attempt to locate the <em:type> node in the RDF doc.
    type_uri = install_rdf.uri("type")
    type_ = install_rdf.get_object(None, type_uri)
    
    if type_ is not None:
        if type_ in translated_types:
            # Make sure we translate back to the normalized version
            return translated_types[type_]
        else:
            err.error(("typedetection",
                       "detect_type",
                       "invalid_em_type"),
                      "Invalid <em:type> value.",
                      """The only valid values for <em:type> are 2, 4, 8, and
                      32. Any other values are either invalid or
                      deprecated.""",
                      "install.rdf")
            return
    else:
        err.info(("typedetection",
                  "detect_type",
                  "no_em:type"),
                 "No <em:type> element found in install.rdf",
                 """It isn't always required, but it is the most
                 reliable method for determining addon type.""",
                 "install.rdf") 
    
    # Dictionaries are weird too, they might not have the obligatory
    # em:type. We can assume that if they have a /dictionaries/ folder,
    # they are a dictionary because even if they aren't, dictionaries
    # have an extraordinarily strict set of rules and file filters that
    # must be passed. It's so crazy secure that it's cool if we use it
    # as kind of a fallback.
    
    package_contents = xpi_package.get_file_data()
    dictionaries = [file_ for file_ in package_contents.keys() if
                    file_.startswith("dictionaries")]
    if dictionaries:
        return PACKAGE_DICTIONARY
    
    
    # There's no type element, so the spec says that it's either a
    # theme or an extension. At this point, we know that it isn't
    # a dictionary, language pack, or multiple extension pack.
    
    extensions = {"jar": "4",
                  "xpi": "2"}
    
    # If the package's extension is listed in the [tiny] extension
    # dictionary, then just return that. We'll validate against that
    # addon type's layout later. Better to false positive than to false
    # negative.
    if xpi_package.extension in extensions:
        # Make sure it gets translated back to the normalized version
        install_rdf_type = extensions[xpi_package.extension]
        return translated_types[install_rdf_type]
    


def detect_opensearch(package):
    "Detect, parse, and validate an OpenSearch provider"
    
    # Parse the file.
    try:
        srch_prov = parse(package)
    except:
        # Don't worry that it's a catch-all exception handler; it failed
        # and that's all that matters.
        return {"failure": True,
                "decided": False,
                "error": "There was an error parsing the file."}
    
    # Make sure that the root element is OpenSearchDescription.
    if srch_prov.documentElement.tagName != "OpenSearchDescription":
        return {"failure": True,
                "decided": False, # Sketch, but we don't really know.
                "error": "Provider is not a valid OpenSearch provider"}


    # Per bug 617822
    if not srch_prov.documentElement.hasAttribute("xmlns"):
        return {"failure": True,
                "error": "Missing XML Namespace"}

    if srch_prov.documentElement.attributes["xmlns"].value not in (
                    'http://a9.com/-/spec/opensearch/1.0/',
                    'http://a9.com/-/spec/opensearch/1.1/',
                    'http://a9.com/-/spec/opensearchdescription/1.1/',
                    'http://a9.com/-/spec/opensearchdescription/1.0/'):
        return {"failure": True,
                "error": "Invalid XML Namespace"}


    # Make sure that there is exactly one ShortName.
    if not srch_prov.documentElement.getElementsByTagName("ShortName"):
        return {"failure": True,
                "error": "Missing <ShortName> element"}
    
    
    # Make sure that there is exactly one Description.
    if not srch_prov.documentElement.getElementsByTagName("Description"):
        return {"failure": True,
                "error": "Missing <Description> element"}
    
    # Grab the URLs and make sure that there is at least one.
    urls = srch_prov.documentElement.getElementsByTagName("Url")
    if not urls:
        return {"failure": True,
                "error": "Missing <Url /> elements"}
    
    acceptable_mimes = ("text/html", "application/xhtml+xml")
    acceptable_urls = [url for url in urls if url.hasAttribute("type") and
                          url.attributes["type"].value in acceptable_mimes]

    # At least one Url must be text/html
    if not acceptable_urls:
        return {"failure": True,
                "error": "No <Url /> elements of HTML type (i.e.: text/html)"}

    # Make sure that each Url has the require attributes.
    for url in acceptable_urls:

        # If the URL is listed as rel="self", skip over it.
        if url.hasAttribute("rel") and url.attributes["rel"].value == "self":
            continue
        
        if url.hasAttribute("method") and \
           url.attributes["method"].value.upper() not in ("GET", "POST"):
            return {"failure": True,
                    "error": "An invalid HTTP method was set for <Url />"}

        # Test for attribute presence.
        if not url.hasAttribute("template"):
            return {"failure": True,
                    "error": "<Url /> element missing template attribute"}
        
        url_template = url.attributes["template"].value
        if url_template[:4] != "http":
            return {"failure": True,
                    "error": "<Url /> contains invalid template (not HTTP)"}

        # Make sure that there is a {searchTerms} placeholder in the
        # URL template.
        found_template = url_template.count("{searchTerms}") > 0
        
        # If we didn't find it in a simple parse of the template=""
        # attribute, look deeper at the <Param /> elements.
        if not found_template:
            for param in url.getElementsByTagName("Param"):
                # As long as we're in here and dependent on the
                # attributes, we'd might as well validate them.
                attribute_keys = param.attributes.keys()
                if not "name" in attribute_keys or \
                   not "value" in attribute_keys:
                    return {"failure": True,
                            "error": "<Param /> missing attributes."}
                
                param_value = param.attributes["value"].value
                if param_value.count("{searchTerms}"):
                    found_template = True
                    
                    # Since we're in a validating spirit, continue
                    # looking for more errors and don't break
        
        # If the template still hasn't been found...
        if not found_template:
            tpl = url.attributes["template"].value
            return {"failure": True,
                    "error": "The template for template '%s' is missing" % tpl}
    
    # Make sure there are no updateURL elements
    if srch_prov.getElementsByTagName("updateURL"):
        return {"failure": True,
                "error": "<updateURL> elements are banned from search"}
    
    # The OpenSearch provider is valid!
    return {"failure": False,
            "error": None}
    
    
