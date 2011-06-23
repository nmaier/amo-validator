from validator.chromemanifest import ChromeManifest


MANIFEST = """
content regular chrome/content
overlay chrome://browser/content/browser.xul chrome://regular/content/overlay.xul
overlay chrome://browser/content/browser.xul chrome://regular/content/
content flagged chrome/content appversion=1.0
overlay chrome://browser/content/browser.xul chrome://flagged/content/overlay.xul appversion=1.0
overlay chrome://browser/content/browser.xul chrome://flagged/content/ appversion=1.0
content trailing chrome/content/
overlay chrome://browser/content/browser.xul chrome://trailing/content/overlay.xul
overlay chrome://browser/content/browser.xul chrome://trailing/content/
content jarred jar:chrome.jar!/chrome/content/
overlay chrome://browser/content/browser.xul chrome://jarred/content/overlay.xul
overlay chrome://browser/content/browser.xul chrome://jarred/content/
"""


def test_get_package():
    manifest = ChromeManifest(MANIFEST)

    assert manifest.get_package("chrome://regular/content/") == ("regular", "/content/")
    assert manifest.get_package("chrome://flagged/content/") == ("flagged", "/content/")
    assert manifest.get_package("chrome://trailing/content/") == ("trailing", "/content/")
    assert manifest.get_package("chrome://jarred/content/") == ("jarred", "/content/")
    

def _do_test_overlay_package(package, base):
    manifest = ChromeManifest(MANIFEST)

    # fully specified
    full = "chrome://%s/content/overlay.xul" % package
    assert full in manifest.overlays
    assert manifest.resolve(full) == base + "/overlay.xul"

    # default xul rewriting
    default = "chrome://%s/content/" % package
    default_resolved = "%s/%s.xul" % (base, package)
    assert default in manifest.overlays
    assert manifest.resolve(default) == default_resolved

    # resolving relative urls according to base uri
    full2 = "chrome://%s/content/first/overlay.xul" % package
    assert manifest.resolve("overlay2.xul",
                            full
                            ) == base + "/overlay2.xul"
    assert manifest.resolve("../second/overlay2.xul",
                            full2
                            ) == base + "/second/overlay2.xul"

def test_overlay_regular():
    """Make sure that regular overlays properly register and resolve"""

    _do_test_overlay_package("regular", "chrome/content")
    
def test_overlay_flagged():
    """Make sure that overlays/packages with manifest flags properly register and resolve"""
    
    _do_test_overlay_package("flagged", "chrome/content")

def test_overlay_trailing():
    """Make sure that overlays/packages with trailing slashes properly register and resolve"""
    
    _do_test_overlay_package("trailing", "chrome/content")

def test_overlay_jarred():
    """Make sure that overlays/packages with jar: URIs trailing slashes properly register and resolve"""
    
    _do_test_overlay_package("jarred", "jar:chrome.jar!/chrome/content")

