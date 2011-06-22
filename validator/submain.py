import os
import re
from StringIO import StringIO
from xml.dom.minidom import parseString as XML
from xml.dom import Node

from validator.typedetection import detect_type
from validator.opensearch import detect_opensearch
from validator.chromemanifest import ChromeManifest
from validator.rdf import RDFParser
from validator.xpi import XPIManager
from validator import decorator

from constants import *

types = {0: "Unknown",
         1: "Extension/Multi-Extension",
         2: "Theme",
         3: "Dictionary",
         4: "Language Pack",
         5: "Search Provider"}

assumed_extensions = {"jar": PACKAGE_THEME,
                      "xml": PACKAGE_SEARCHPROV}


def prepare_package(err, path, expectation=0, for_appversions=None):
    "Prepares a file-based package for validation."

    # Test that the package actually exists. I consider this Tier 0
    # since we may not even be dealing with a real file.
    if err and not os.path.isfile(path):
        err.error(("main",
                   "prepare_package",
                   "not_found"),
                  "The package could not be found")
        return

    # Pop the package extension.
    package_extension = os.path.splitext(path)[1]
    package_extension = package_extension.lower()

    if package_extension == ".xml":
        return test_search(err, path, expectation)

    # Test that the package is an XPI.
    if package_extension not in (".xpi", ".jar"):
        if err:
            err.error(("main",
                       "prepare_package",
                       "unrecognized"),
                      "The package is not of a recognized type.")
        return False

    package = open(path, "rb")
    output = test_package(err, package, path, expectation,
                          for_appversions)
    package.close()

    return output


def test_search(err, package, expectation=0):
    "Tests the package to see if it is a search provider."

    expected_search_provider = expectation in (PACKAGE_ANY,
                                               PACKAGE_SEARCHPROV)

    # If we're not expecting a search provider, warn the user and stop
    # testing it like a search provider.
    if not expected_search_provider:
        return err.warning(("main",
                            "test_search",
                            "extension"),
                           "Unexpected file extension.")

    # Is this a search provider?
    detect_opensearch(err, package, listed=err.get_resource("listed"))

    if expected_search_provider and not err.failed():
        err.set_type(PACKAGE_SEARCHPROV)
        err.notice(("main",
                    "test_search",
                    "confirmed"),
                   "OpenSearch provider confirmed.")


def test_package(err, file_, name, expectation=PACKAGE_ANY,
                 for_appversions=None):
    "Begins tests for the package."

    # Load up a new instance of an XPI.
    try:
        package = XPIManager(file_, mode="r", name=name)
    except:
        # Die on this one because the file won't open.
        return err.error(("main",
                          "test_package",
                          "unopenable"),
                         "The XPI could not be opened.")

    # Test the XPI file for corruption.
    if package.test():
        return err.error(("main",
                          "test_package",
                          "corrupt"),
                         "XPI package appears to be corrupt.")

    if package.extension in assumed_extensions:
        assumed_type = assumed_extensions[package.extension]
        # Is the user expecting a different package type?
        if not expectation in (PACKAGE_ANY, assumed_type):
            err.error(("main",
                       "test_package",
                       "unexpected_type"),
                      "Unexpected package type (found theme)")

    # Test the install.rdf file to see if we can get the type that way.
    has_install_rdf = "install.rdf" in package
    if has_install_rdf:
        _load_install_rdf(err, package, expectation)

    return test_inner_package(err, package, for_appversions)


def _load_install_rdf(err, package, expectation):
    # Load up the install.rdf file.
    install_rdf_data = package.read("install.rdf")

    if re.search('<!doctype', install_rdf_data, re.I):
        err.save_resource("bad_install_rdf", True)
        return err.error(("main",
                          "test_package",
                          "doctype_in_installrdf"),
                         "DOCTYPEs are not permitted in install.rdf",
                         "The add-on's install.rdf file contains a DOCTYPE. "
                         "It must be removed before your add-on can be "
                         "validated.",
                         filename="install.rdf")

    install_rdf = RDFParser(install_rdf_data)

    if install_rdf.rdf is None or not install_rdf:
        return err.error(("main",
                          "test_package",
                          "cannot_parse_installrdf"),
                         "Cannot Parse install.rdf",
                         "The install.rdf file could not be parsed.",
                         filename="install.rdf")
    else:
        err.save_resource("has_install_rdf", True, pushable=True)
        err.save_resource("install_rdf", install_rdf, pushable=True)

    # Load up the results of the type detection
    results = detect_type(err, install_rdf, package)

    if results is None:
        return err.error(("main",
                          "test_package",
                          "undeterminable_type"),
                         "Unable to determine add-on type",
                         "The type detection algorithm could not determine "
                         "the type of the add-on.")
    else:
        err.set_type(results)

    # Compare the results of the low-level type detection to
    # that of the expectation and the assumption.
    if not expectation in (PACKAGE_ANY, results):
        err.warning(("main",
                     "test_package",
                     "extension_type_mismatch"),
                    "Extension Type Mismatch",
                    'Type "%s" expected, found "%s")' % (
                                                    types[expectation],
                                                    types[results]))


def populate_chrome_manifest(err, xpi_package):
    "Loads the chrome.manifest if it's present"

    if "chrome.manifest" in xpi_package:
        chrome_data = xpi_package.read("chrome.manifest")
        chrome = ChromeManifest(chrome_data)
        err.save_resource("chrome.manifest", chrome, pushable=True)

def populate_overlay_tags(err, xpi_package):
    cm = err.get_resource("chrome.manifest")
    if not cm:
        return

    def get_content(manager, location):
        if location.startswith("jar:"):
            jar, location = location.split("!", 2)
            jar = jar[4:]
            manager = StringIO(manager.read(jar))
            manager = XPIManager(manager, mode="r", name=jar)
        if location.startswith("/"):
            location = location[1:]
        return manager.read(location)

    def process_overlay(err, manager, overlay):
        resolved = cm.resolve(overlay)
        if not resolved:
            return

        try:
            xml = XML(get_content(manager, cm.resolve(overlay)))
            for node in xml.childNodes:
                if node.nodeType != Node.PROCESSING_INSTRUCTION_NODE or node.target != "xul-overlay":
                    continue
                try:
                    uri = cm.resolve(re.match(r'href=(["\'])(.+?)\1', node.data).group(2), overlay)
                    if uri:
                        for rv in process_overlay(err, manager, uri):
                            yield rv
                except:
                    pass
            for node in xml.getElementsByTagName("script"):
                if not node.hasAttribute("src"):
                    # No need to tag snippets
                    # Those will be handled by the tagged overlay
                    continue
                uri = cm.parse_uri(node.getAttribute("src"), overlay)
                if not uri:
                    continue
                resolved = cm.resolve(uri)
                if not resolved:
                    continue
                yield resolved
        except:
            # XXX may want to report broken overlays at this point, or somewhere else
            pass

    overlays = []
    tags = {}
    for o in cm.overlays:
        overlays.extend(process_overlay(err, xpi_package, o))
    for o in overlays:
        package = "<main>"
        location = o
        if location.startswith("jar:"):
            package, location = location.split("!", 2)
            package = package[4:]
        try:
            tags[package].append(location)
        except KeyError:
            tags[package] = [location]
    err.save_resource("overlay_tags", tags)

def test_inner_package(err, xpi_package, for_appversions=None):
    "Tests a package's inner content."

    populate_chrome_manifest(err, xpi_package)
    populate_overlay_tags(err, xpi_package)

    # Iterate through each tier.
    for tier in sorted(decorator.get_tiers()):

        # Let the error bundler know what tier we're on.
        err.set_tier(tier)

        # Iterate through each test of our detected type.
        for test in decorator.get_tests(tier, err.detected_type):
            # Test whether the test is app/version specific.
            if test["versions"] is not None:
                # If the test's version requirements don't apply to the add-on,
                # then skip the test.
                if not err.supports_version(test["versions"]):
                    continue

                # If the user's version requirements don't apply to the test or
                # to the add-on, then skip the test.
                if (for_appversions and
                    not (err._compare_version(requirements=for_appversions,
                                              support=test["versions"]) and
                         err.supports_version(for_appversions))):
                    continue

            # Save the version requirements to the error bundler.
            err.version_requirements = test["versions"]

            test_func = test["test"]
            if test["simple"]:
                test_func(err)
            else:
                # Pass in:
                # - Error Bundler
                # - Package listing
                # - A copy of the package itself
                test_func(err, xpi_package)

        # Return any errors at the end of the tier if undetermined.
        if err.failed(fail_on_warnings=False) and not err.determined:
            err.unfinished = True
            err.discard_unused_messages(ending_tier=tier)
            return err

    # Return the results.
    return err
