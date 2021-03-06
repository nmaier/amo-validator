import sys
import os
import chardet
import json
import fnmatch
from StringIO import StringIO

from validator import decorator
from validator.chromemanifest import ChromeManifest
from validator.xpi import XPIManager
from validator.constants import *

import validator.testcases.l10n.dtd as dtd
import validator.testcases.l10n.properties as properties


# The threshold that determines the number of entities that must not be
# missing from the package.
L10N_THRESHOLD = 0.35
L10N_SIMILAR_THRESHOLD = 0.9 # For en_US/en_GB kind of stuff

# Only warn about unchanged entities longer than this number of characters.
L10N_LENGTH_THRESHOLD = 3

# To avoid noise, this value ensures that the percent of unchanged entities
# is not inflated due to small numbers of entities.
L10N_MIN_ENTITIES = 18

LOCALE_CACHE = {}

def _get_locales(err, xpi_package):
    "Returns a list of locales from the chrome.manifest file."
    
    # Retrieve the chrome.manifest if it's cached.
    if err is not None and \
       err.get_resource("chrome.manifest"): # pragma: no cover
        chrome = err.get_resource("chrome.manifest")
    else:
        chrome_data = xpi_package.read("chrome.manifest")
        chrome = ChromeManifest(chrome_data)
        if err is not None:
            err.save_resource("chrome.manifest", chrome)
        
    pack_locales = chrome.get_triples("locale")
    locales = {}
    # Find all of the locales referenced in the chrome.manifest file.
    for locale in pack_locales:
        locale_jar = locale["object"].split()

        location = locale_jar[-1]
        if not location.startswith("jar:"):
            continue
        full_location = location[4:].split("!")
        locale_desc = {"predicate": locale["predicate"],
                       "path": full_location[0],
                       "target": full_location[1],
                       "name": locale_jar[0]}
        locale_name = "%s:%s" % (locale["predicate"], locale_jar[0])
        if locale_name not in locales:
            locales[locale_name] = locale_desc
    
    return locales

def _get_locale_manager(err, addon, path, files, no_cache=False):
    "Returns the XPIManager object for a locale"

    if path in LOCALE_CACHE and not no_cache:
        return LOCALE_CACHE[path]

    if path not in files:
        err.warning(("testcases_l10ncompleteness",
                     "_get_locale_manager",
                     "manager_absent"),
                    "Listed locale does not exist",
                    ["A locale JAR is listed in chrome.manifest, but it could "
                     "not be located. Check the spelling and capitalization "
                     "of the path.",
                     "Missing JAR: %s" % path],
                    filename="chrome.manifest")
        return None
    jar = StringIO(addon.read(path))
    locale = XPIManager(jar, path)

    if not no_cache:
        LOCALE_CACHE[path] = locale
    return locale

@decorator.register_test(tier=3)
def test_xpi(err, package_contents, xpi_package):
    """Tests an XPI (or JAR, really) for L10n completeness"""
    
    # Skip over incompatible (or unnecessary) package types.
    if err.detected_type not in (PACKAGE_EXTENSION,
                                 PACKAGE_THEME) or \
       err.is_nested_package():
        # NOTE : Should we also do this with PACKAGE_MULTI?
        return None
    
    # Don't even both with the test(s) if there's no chrome.manifest.
    if "chrome.manifest" not in package_contents:
        return None
    
    locales = _get_locales(err, xpi_package);
    
    # We need at least a reference and a target.
    if len(locales) < 2:
        return
    
    ref_name = "en-US"
    # Fall back on whatever comes first.
    if ref_name not in locales:
        ref_name = locales.keys()[0]

    reference = locales[ref_name]
    reference_locale = _get_locale_manager(err,
                                           xpi_package,
                                           reference["path"],
                                           package_contents)
    # Loop through the locales and test the valid ones.
    for name, locale in locales.items():
        # Ignore the reference locale
        if locale["name"] == ref_name:
            continue
        
        target_locale = _get_locale_manager(err,
                                            xpi_package,
                                            locale["path"],
                                            package_contents)
        if target_locale is None:
            continue
        split_target = locale["name"].split("-")
        
        # Isolate each of the target locales' results.
        results = _compare_packages(reference_locale,
                                    target_locale,
                                    reference["target"],
                                    locale["target"])
        _aggregate_results(err,
                           results,
                           locale,
                           ref_name.startswith(split_target[0]))

    # Clear the cache at the end of the test
    L10N_CACHE = {}

@decorator.register_test(tier=3, expected_type=PACKAGE_LANGPACK)
def test_lp_xpi(err, package_contents, xpi_package):
    "Tests a language pack for L10n completeness"
    
    # Don't even both with the test(s) if there's no chrome.manifest.
    if "chrome.manifest" not in package_contents:
        return None

    locales = _get_locales(err, xpi_package);
    
    # Get the reference packages.
    references = []
    support_references = err.get_resource("supports")
    if not support_references:
        references.append("firefox")
        err.info(("testcases_l10ncompleteness",
                  "test_lp_xpi",
                  "missing_app_support"),
                 "Supported app missing during L10n completeness.",
                 """While testing for L10n comleteness, a list of
                 supported applications for the language pack was not
                 found. This is likely because there are no listed
                 <em:targetApplication> elements in the install.rdf
                 file.""")
    else:
        for support in support_references:
            ref_xpi = XPIManager(os.path.join(os.path.dirname(__file__),
                                              "langpacks/%s.xpi" % support))
            ref_xpi.app_name = support
            reference_locales = _get_locales(None, ref_xpi)

            references.append((ref_xpi, reference_locales))
            
    # Iterate each supported reference package
    for (ref_xpi, ref_locales) in references:
        # Iterate each locale in each supported reference package
        ref_pack = _get_locale_manager(err,
                                       ref_xpi,
                                       "en-US.jar",
                                       ref_xpi.get_file_data(),
                                       no_cache=True)
        for ref_locale_name in ref_locales:
            ref_locale = ref_locales[ref_locale_name]
            ref_predicate = ref_locale["predicate"]
            corresp_locales = [locales[name] for name
                               in locales
                               if locales[name]["predicate"] == ref_predicate]
            # If we found no matching locale, then it's missing from the pack
            if not corresp_locales:
                err.warning(("testcases_l10ncompleteness",
                             "test_lp_xpi",
                             "find_corresponding_locale"),
                            "Could not find corresponding locale",
                            ["A locale was found in the reference package, "
                             "however it was not found in the target package.",
                             "Missing locale: %s" % ref_predicate],
                            filename="chrome.manifest")
                continue
            
            target_locale = corresp_locales[0]
            target_pack = _get_locale_manager(err,
                                              xpi_package,
                                              target_locale["path"],
                                              package_contents)
            if target_pack is None:
                continue

            results = _compare_packages(reference=ref_pack,
                                        target=target_pack,
                                        ref_base=ref_locale["target"],
                                        locale_base=target_locale["target"])

            # Report the findings after each supported app's locale
            _aggregate_results(err, results, target_locale)
    
    # Clear the cache at the end of the test
    LOCALE_CACHE = {}

def _compare_packages(reference, target, ref_base="", locale_base=""):
    "Compares two L10n-compatible packages to one another."
    
    ref_files = reference.get_file_data()
    tar_files = target.get_file_data()
    
    results = []
    total_entities = 0
    
    ref_base = ref_base.lstrip("/")
    locale_base = locale_base.lstrip("/")
    
    l10n_docs = ("dtd", "properties", "xhtml", "ini", "inc")
    parsable_docs = ("dtd", "properties")
    
    for name, file_data in ref_files.items():
        
        entity_count = 0
        
        # Skip directory entries.
        if name.endswith("/"): # pragma: no cover
            continue

        # Ignore files not considered reference files.
        if ref_base and not name.startswith(ref_base):
            continue
        
        extension = name.split(".")[-1]
        if extension not in l10n_docs:
            continue
        parsable = extension in parsable_docs
        
        if parsable:
            ref_doc = _parse_l10n_doc(name,
                                      reference.read(name),
                                      no_encoding=True)
        else:
            ref_doc = ()
        
        tar_name = locale_base + name[len(ref_base):]
        if tar_name not in tar_files:
            results.append({"type": "missing_files",
                            "entities": len(ref_doc),
                            "filename": tar_name})
            continue
        
        if not parsable:
            continue
        
        tar_doc = _parse_l10n_doc(tar_name, target.read(tar_name))
        
        if not tar_doc.expected_encoding:
            results.append({"type": "unexpected_encoding",
                            "filename": tar_name,
                            "expected_encoding": tar_doc.suitable_encoding,
                            "encoding": tar_doc.found_encoding})

        missing_entities = []
        unchanged_entities = []
        
        for rname, rvalue, rline in ref_doc.items:
            entity_count += 1
            
            if rname not in tar_doc.entities:
                missing_entities.append(rname)
                continue
            
            if rvalue == tar_doc.entities[rname] and \
               len(rvalue) > L10N_LENGTH_THRESHOLD and \
               not fnmatch.fnmatch(rvalue, "http*://*"):
                
                unchanged_entities.append((rname, rline))
                continue
            
        
        if missing_entities:
            results.append({"type": "missing_entities",
                            "entities": len(missing_entities),
                            "filename": tar_name,
                            "missing_entities": missing_entities})
        if unchanged_entities:
            results.append({"type": "unchanged_entity",
                            "entities": len(unchanged_entities),
                            "filename": tar_name,
                            "unchanged_entities": unchanged_entities})
        
        results.append({"type": "file_entity_count",
                        "filename": tar_name,
                        "entities": entity_count})
        
        total_entities += entity_count
        
    
    results.append({"type": "total_entities",
                    "entities": total_entities})
    return results
    

def _parse_l10n_doc(name, doc, no_encoding=False):
    "Parses an L10n document."
    
    extension = name.split(".")[-1].lower()
    
    handlers = {"dtd": dtd.DTDParser,
                "properties": properties.PropertiesParser}
    # These are expected encodings for the various files.
    handler_formats = ("ASCII", "UTF-8")
    if extension not in handlers:
        return None
    
    wrapper = StringIO(doc)
    loc_doc = handlers[extension](wrapper)
    
    # Allow the parse to specify files to skip for encoding checks
    if not no_encoding:
        encoding = chardet.detect(doc)
        if not encoding \
          or not "encoding" in encoding \
          or not encoding["encoding"]:
            encoding = ""
        else:
            encoding = encoding["encoding"].upper()
        loc_doc.expected_encoding = encoding in handler_formats
        loc_doc.found_encoding = encoding
        loc_doc.suitable_encoding = handler_formats

    return loc_doc

def _aggregate_results(err, results, locale, similar=False, base="en-US"):
    """Compiles the errors and warnings in the L10n results list into
    error bundler errors and warnings."""
    
    total_entities = 0
    unchanged_entities = 0
    unchanged_entity_list = {}
    entity_count = {}
    unexpected_encodings = []
    
    for ritem in results:
        if "filename" in ritem:
            rfilename = ritem["filename"]
        
        rtype = ritem["type"]
        if rtype == "missing_files":
            err.warning(("testcases_l10ncompleteness",
                        "_aggregate_results",
                        "missing_file"),
                       "Missing translation file",
                       ["""Localizations must include a translated copy
                        of each file in the reference locale. The
                        required files may vary from target application
                        to target application.""",
                        "%s missing translation file (%s)" % (locale["path"],
                                                              rfilename)],
                      [locale["path"]])
        elif rtype == "missing_entities":
            err.warning(("testcases_l10ncompleteness",
                         "_aggregate_results",
                         "missing_translation_entity"),
                        "Missing translation entity",
                        ["""Localizations must include a translated copy
                         of each entity from each file in the reference
                         locale. The required files may vary from target
                         application to target application.""",
                         "%s missing %s in %s" %
                             (locale["path"],
                              ", ".join(ritem["missing_entities"]),
                              rfilename)],
                        [locale["path"], rfilename])
        elif rtype == "unchanged_entity":
            filename = ritem["filename"]
            if not filename in unchanged_entity_list:
                unchanged_entity_list[filename] = {"count": 0,
                                                   "entities": []}
            unchanged = unchanged_entity_list[filename]
            unchanged["count"] += ritem["entities"]
            unchanged["entities"].extend(ritem["unchanged_entities"])
        elif rtype == "total_entities":
            total_entities += ritem["entities"]
        elif rtype == "file_entity_count":
            entity_count[ritem["filename"]] = ritem["entities"]
        elif rtype == "unexpected_encoding":
            unexpected_encodings.append(
                    (ritem["filename"],
                     ritem["encoding"],
                     ", ".join(ritem["expected_encoding"])))
    
    agg_unchanged = []
    if not similar:
        unchanged_percentage = L10N_THRESHOLD
    else:
        unchanged_percentage = L10N_SIMILAR_THRESHOLD
    for name, count in entity_count.items():
        if name not in unchanged_entity_list or \
           count == 0:
            continue
        
        unchanged = unchanged_entity_list[name]
        total_adjusted = max(count, L10N_MIN_ENTITIES)
        percentage = float(unchanged["count"]) / float(total_adjusted)
        if percentage >= unchanged_percentage:
            agg_unchanged.append(
                    "%s: %d/%d entities unchanged (%s) at %d percent" %
                    (name,
                     unchanged["count"],
                     count,
                     ", ".join(["%s (%d)" % (e, line)
                                for e, line
                                in unchanged["entities"]]),
                     percentage * 100))
    
    if agg_unchanged:
        err.warning(("testcases_l10ncompleteness",
                     "_aggregate_results",
                     "unchnged_entities"),
                    "Unchanged translation entities",
                    ["""Localizations must include a translated copy of each
                     entity from each file in the reference locale. These
                     translations SHOULD differ from the localized text in the
                     reference package.""",
                     agg_unchanged],
                    [locale["path"], locale["target"]])

    if unexpected_encodings:
        # Compile all of the encoding errors into one nice warning.
        compilation = ["Detected files:"]
        for target in unexpected_encodings:
            compilation.append("%s\n Found: %s\n Expected: %s" % target)

        err.warning(("testcases_l10ncompleteness",
                     "_aggregate_results",
                     "unexpected_encodings"),
                    "Unexpected encodings in L10n files",
                    ["Localization files were encountered that used encodings "
                     "that are not characteristic of those types of files.",
                     "\n".join(compilation),
                     "Localization files with the wrong encoding can cause "
                     "issues with locales that include non-ASCII characters."],
                    [locale["path"], locale["target"]])

