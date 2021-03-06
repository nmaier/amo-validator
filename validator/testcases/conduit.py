import fnmatch

from validator import decorator
from validator.chromemanifest import ChromeManifest
from validator.constants import *

@decorator.register_test(1)
def test_conduittoolbar(err, package_contents=None, xpi_manager=None):
    "Find and blacklist Conduit toolbars"
    
    # Ignore non-extension types
    if err.detected_type in (PACKAGE_ANY,
                             PACKAGE_THEME,
                             PACKAGE_SEARCHPROV):
        return None
    
    # Tests regarding the install.rdf file.
    if err.get_resource("has_install_rdf"):
        
        #Go out and fetch the install.rdf instance object
        install = err.get_resource("install_rdf")
        
        # Define a list of specifications to search for Conduit with
        parameters = {
            "http://www.conduit.com/": install.uri("homepageURL"),
            "Conduit Ltd.": install.uri("creator"),
            "More than just a toolbar.": install.uri("description")}
        
        # Iterate each specification and test for it.
        for k, uri_reference in parameters.items():
            # Retrieve the value
            results = install.get_object(None, uri_reference)
            # If the value exists, test for the appropriate content
            if results == k:
                err.reject = True
                err_mesg = "Conduit value (%s) found in install.rdf" % k
                return err.warning(("testcases_conduit",
                                    "test_conduittoolbar",
                                    "detected_rdf"),
                                   "Detected Conduit toolbar.",
                                   err_mesg,
                                   "install.rdf")
        
        # Also test for the update URL
        update_url_value = "https://ffupdate.conduit-services.com/"
        
        results = install.get_object(None, install.uri("updateURL"))
        if results and results.startswith(update_url_value):
            err.reject = True
            return err.warning(("testcases_conduit",
                                "test_conduittoolbar",
                                "detected_updateurl"),
                               "Detected Conduit toolbar.",
                               "Conduit update URL found in install.rdf.",
                               "install.rdf")
    
        
    # Do some matching on the files in the package
    conduit_files = ("components/Conduit*",
                     "searchplugin/conduit*")
    for file_ in package_contents:
        for bad_file in conduit_files:
            # If there's a matching file, it's Conduit
            if fnmatch.fnmatch(file_, bad_file):
                err.reject = True
                return err.warning(("testcases_conduit",
                                    "test_conduittoolbar",
                                    "detected_files"),
                                   "Detected Conduit toolbar.",
                                   "Conduit directory (%s) found." % bad_file)
    
    
    # Do some tests on the chrome.manifest file if it exists
    if "chrome.manifest" in package_contents:
        # Grab the chrome manifest
        if err.get_resource("chrome.manifest"): # pragma: no cover
            # It's cached in the error bundler
            chrome = err.get_resource("chrome.manifest")
        else:
            # Not cached, so we grab it.
            chrome_data = xpi_manager.read("chrome.manifest")
            chrome = ChromeManifest(chrome_data)
            err.save_resource("chrome.manifest", chrome)
        
        # Get all styles for customizing the toolbar
        data = chrome.get_value("style",
                    "chrome://global/content/customizeToolbar.xul")
        
        # If the style exists and it contains "ebtoolbarstyle"...
        if data is not None and \
           data["object"].count("ebtoolbarstyle") > 0:
            err.reject = True
            return err.warning(("testcases_conduit",
                                "test_conduittoolbar",
                                "detected_chrome_manifest"),
                               "Detected Conduit toolbar.",
                               "'ebtoolbarstyle' found in chrome.manifest",
                               "chrome.manifest",
                               line=data["line"],
                               context=chrome.context)
        
        
