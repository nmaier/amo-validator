import os
import re
from urlparse import urlparse, urlunparse

from validator.contextgenerator import ContextGenerator

VALID_OVERLAY_PACKAGES = ["global", "mozapps", "browser", "navigator", "messager", "firebug", "addons"]

# copied and adapted to support chrome-proto from urlparse
def urljoin(base, url, allow_fragments=True):
    """Join a base URL and a possibly relative URL to form an absolute
    interpretation of the latter."""
    if not base:
        return url
    if not url:
        return base
    bscheme, bnetloc, bpath, bparams, bquery, bfragment = \
            urlparse(base, '', allow_fragments)
    scheme, netloc, path, params, query, fragment = \
            urlparse(url, bscheme, allow_fragments)
    if scheme != bscheme:
        return url
    if netloc:
        return urlunparse((scheme, netloc, path,
                                             params, query, fragment))
    netloc = bnetloc
    if path[:1] == '/':
        return urlunparse((scheme, netloc, path,
                                             params, query, fragment))
    if not path:
        path = bpath
        if not params:
            params = bparams
        else:
            path = path[:-1]
            return urlunparse((scheme, netloc, path,
                                                params, query, fragment))
        if not query:
            query = bquery
        return urlunparse((scheme, netloc, path,
                                         params, query, fragment))
    segments = bpath.split('/')[:-1] + path.split('/')
    # XXX The stuff below is bogus in various ways...
    if segments[-1] == '.':
            segments[-1] = ''
    while '.' in segments:
            segments.remove('.')
    while 1:
        i = 1
        n = len(segments) - 1
        while i < n:
            if (segments[i] == '..'
                and segments[i-1] not in ('', '..')):
                del segments[i-1:i+1]
                break
            i = i+1
        else:
            break
    if segments == ['', '..']:
        segments[-1] = ''
    elif len(segments) >= 2 and segments[-1] == '..':
        segments[-2:] = ['']
    return urlunparse((scheme, netloc, '/'.join(segments),
                                     params, query, fragment))


class ChromeManifest(object):
    """This class enables convenient reading and searching of
    chrome.manifest files."""

    def __init__(self, data):
        "Reads an ntriples style chrome.manifest file"

        self.context = ContextGenerator(data)
        self.lines = data.split("\n")

        # Extract the data from the triples in the manifest
        triples = []
        counter = 0

        for line in self.lines:
            line = line.strip()

            counter += 1

            # Skip weird lines.
            if line.startswith("#"):
                continue

            triple = line.split(None, 2)
            if not triple:
                continue
            elif len(triple) == 2:
                triple.append("")
            if len(triple) < 3:
                continue

            triples.append({"subject": triple[0],
                            "predicate": triple[1],
                            "object": triple[2],
                            "line": counter})

        self.triples = triples

        possible_overlays = [{"chrome": t["object"].split(None, 2)[0],
                              "overlay": t["predicate"]}
                             for t in self.get_triples(subject="overlay")]
        valid_overlays = []
        while True:
            chrome = [o["chrome"] for o in valid_overlays]
            def validate_overlay(o):
                [package, d] = self.get_package(o["overlay"])
                if package in VALID_OVERLAY_PACKAGES:
                    return True
                if o['overlay'] in chrome:
                    return True
                return False

            additional_overlays = filter(validate_overlay,
                                         possible_overlays)
            if not additional_overlays:
                break
            valid_overlays += additional_overlays
            possible_overlays = [o for o in possible_overlays
                                 if o not in valid_overlays]
        self.overlays = sorted(o["chrome"] for o in valid_overlays if self.resolve(o["chrome"]))

    def get_value(self, subject=None, predicate=None, object_=None):
        """Returns the first triple value matching the given subject,
        predicate, and/or object"""

        for triple in self.triples:

            # Filter out non-matches
            if (subject and triple["subject"] != subject) or \
               (predicate and triple["predicate"] != predicate) or \
               (object_ and triple["object"] != object_):  # pragma: no cover
                continue

            # Return the first found.
            return triple

        return None

    def get_objects(self, subject=None, predicate=None):
        """Returns a generator of objects that correspond to the
        specified subjects and predicates."""

        for triple in self.triples:

            # Filter out non-matches
            if (subject and
                triple["subject"] != subject) or \
               (predicate and
                triple["predicate"] != predicate):  # pragma: no cover
                continue

            yield triple["object"]

    def get_triples(self, subject=None, predicate=None, object_=None):
        """Returns triples that correspond to the specified subject,
        predicates, and objects."""

        for triple in self.triples:

            # Filter out non-matches
            if subject is not None and triple["subject"] != subject:
                continue
            if predicate is not None and \
               triple["predicate"] != predicate:
                continue
            if object_ is not None and triple["object"] != object_:
                continue

            yield triple

    def parse_uri(self, uri, baseUri=None):
        """Attempt to parse a chrome uri"""

        try:
            if baseUri:
                uri = urljoin(baseUri, uri)
            p = urlparse(uri)
            return uri
        except:
            return None
            
    def get_package(self, uri, baseUri=None):
        """Get the package from a chrome URI"""

        if baseUri:
            uri = urljoin(baseUri, uri)
        p = urlparse(uri)
        return p.netloc, p.path

    def resolve(self, uri, baseUri=None):
        """Resolve a chrome URI to a inner-XPI file path"""

        package, path = self.get_package(uri, baseUri)
        m = re.match(r"[\/]?(content|skin)([\/].+)?$", path)
        if not m:
            return None
        ptype = m.group(1)
        ipath = m.group(2)

        try:
            trip = self.get_triples(subject=ptype, predicate=package).next()
        except:
            return None
        base = trip["object"].split(None, 2)[0]

        if not ipath:
            # Shortcut: chrome://pack/content/ -> chrome://pack/content/pack.xul
            if ptype == "content":
                ipath = trip["object"] + package + ".xul"

            # Shortcut: chrome://pack/skin/ -> chrome://pack/skin/pack.css
            elif ptype == "skin":
                ipath = trip["object"] + package + ".css"

            return None
        if ipath.startswith("/") and base.endswith("/"):
            ipath = ipath[1:]
        return base + ipath


