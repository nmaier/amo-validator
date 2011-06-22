from js_helper import _do_test_raw


def test_pollution():
    """Make sure that the JS namespace pollution tests are done properly."""

    assert not _do_test_raw("""
    a = "foo";
    b = "foo";
    c = "foo";
    """, ignore_pollution=False).failed()

    assert _do_test_raw("""
    a = "foo";
    b = "foo";
    c = "foo";
    d = "foo";
    """, ignore_pollution=False).failed()


def test_pollution_jsm():
    """
    Make sure that JSM files don't have to worry about namespace pollution.
    """

    assert not _do_test_raw("""
    a = "foo";
    b = "foo";
    c = "foo";
    d = "foo";
    """, path="foo.jsm", ignore_pollution=False).failed()

def test_pollution_args():
    """
    Make sure function arguments do not count towards globals, and hence pollution
    """

    assert not _do_test_raw("""
    (function(a) a = "foo")({});
    (function(b) b = "foo")({});
    (function(c) c = "foo")({});
    (function(d) d = "foo")({});
    """, ignore_pollution=False).failed()
