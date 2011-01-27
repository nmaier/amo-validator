import json
import re
import subprocess
# do not use cStringIO as it doesn't support unicode
from StringIO import StringIO

import validator.testcases.javascript.traverser as traverser
from validator.constants import SPIDERMONKEY_INSTALLATION
from validator.contextgenerator import ContextGenerator

JS_ESCAPE = re.compile(r"\\u")
WEIRD_CHARS = [chr(c) for c in range(0,32) if "\r\n\t".find(chr(c)) == -1]

def test_js_file(err, filename, data, line=0):
    "Tests a JS file by parsing and analyzing its tokens"

    if SPIDERMONKEY_INSTALLATION is None or \
       err.get_resource("SPIDERMONKEY") is None: # Default value is False
        return

    before_tier = None
    # Set the tier to 4 (Security Tests)
    if err is not None:
        before_tier = err.tier
        err.tier = 4

    # Get the AST tree for the JS code
    try:
        tree = _get_tree(filename,
                         data,
                         shell=(err and err.get_resource("SPIDERMONKEY")) or
                               SPIDERMONKEY_INSTALLATION,
                         errorbundle=err)

    except JSReflectException as exc:
        str_exc = str(exc).strip("'\"")
        if "SyntaxError" in str_exc:
            err.warning(("testcases_scripting",
                         "test_js_file",
                         "syntax_error"),
                         "JavaScript Syntax Error",
                         ["A syntax error in the JavaScript halted validation "
                          "of that file.",
                          "Message: %s" % str_exc[15:-1]],
                         filename=filename,
                         line=exc.line,
                         context=ContextGenerator(data))
        elif "InternalError: too much recursion" in str_exc:
            err.notice(("testcases_scripting",
                        "test_js_file",
                        "recursion_error"),
                       "JS too deeply nested for validation",
                       "A JS file was encountered that could not be valiated "
                       "due to limitations with Spidermonkey. It should be "
                       "manually inspected.",
                       filename=filename)
        else:
            err.warning(("testcases_scripting",
                         "test_js_file",
                         "retrieving_tree"),
                        "JS reflection error prevented validation",
                        ["An error in the JavaScript file prevented it from "
                         "being properly read by the Spidermonkey JS engine.",
                         str(exc)],
                        filename=filename)
            import sys
            etype, err, tb = sys.exc_info()
            raise exc, None, tb

        if before_tier:
            err.tier = before_tier
        return

    if tree is None:
        if before_tier:
            err.tier = before_tier
        return None

    context = ContextGenerator(data)
    if traverser.DEBUG:
        _do_test(err=err, filename=filename, line=line, context=context,
                 tree=tree)
    else:
        try:
            _do_test(err=err, filename=filename, line=line, context=context,
                     tree=tree)
        except:
            # We do this because the validator can still be damn unstable.
            pass

    _regex_tests(err, data, filename)

    # Reset the tier so we don't break the world
    if err is not None:
        err.tier = before_tier

def test_js_snippet(err, data, filename, line=0):
    "Process a JS snippet by passing it through to the file tester."

    # Wrap snippets in a function to prevent the parser from freaking out
    # when return statements exist without a corresponding function.
    data = "(function(){%s\n})()" % data

    test_js_file(err, filename, data, line)

def _do_test(err, filename, line, context, tree):
    t = traverser.Traverser(err, filename, line, context=context)
    t.run(tree)

def _regex_tests(err, data, filename):

    c = ContextGenerator(data)

    np_warning = "Network preferences may not be modified."

    errors = {"globalStorage\\[.*\\].password":
                  "Global Storage may not be used to store passwords.",
              "network\\.http": np_warning,
              "extensions\\.blocklist\\.url": np_warning,
              "extensions\\.blocklist\\.level": np_warning,
              "extensions\\.blocklist\\.interval": np_warning,
              "general\\.useragent": np_warning}

    for regex, message in errors.items():
        reg = re.compile(regex)
        match = reg.search(data)

        if match:
            line = c.get_line(match.start())
            err.warning(("testcases_scripting",
                         "regex_tests",
                         "compiled_error"),
                        "Potentially malicious JS",
                        message,
                        filename=filename,
                        line=line,
                        context=c)


class JSReflectException(Exception):
    "An exception to indicate that tokenization has failed"

    def __init__(self, value):
        self.value = value
        self.line = None

    def __str__(self):
        return repr(self.value)

    def line_num(self, line_num):
        "Set the line number and return self for chaining"
        self.line = int(line_num)
        return self

def strip_weird_chars(chardata, err=None, name=""):
    line_num = 1
    out_code = StringIO()
    has_warned_ctrlchar = False

    for line in chardata.split(u"\n"):
        charpos = 0
        for char in line:
            if char not in WEIRD_CHARS:
                out_code.write(char)
            elif not has_warned_ctrlchar and err is not None:
                err.warning(("testcases_scripting",
                             "_get_tree",
                             "control_char_filter"),
                             "Invalid control character in JS file",
                             "An invalid character (ASCII 0-31, except CR "
                             "and LF) has been found in a JS file. These "
                             "are considered unsafe and should be removed.",
                             filename=name,
                             line=line_num,
                             column=charpos,
                             context=ContextGenerator(chardata))
                has_warned_ctrlchar = True

            charpos += 1

        out_code.write(u"\n")
        line_num += 1
    return out_code.getvalue()

def _get_tree(name, code, shell=SPIDERMONKEY_INSTALLATION, errorbundle=None):
    "Returns an AST tree of the JS passed in `code`."

    if not code:
        return None

    # Sanitize input
    code = strip_weird_chars(code, errorbundle, name=name)
    code = JS_ESCAPE.sub("u", json.dumps(code))

    # Because of json.dumps code is already ascii
    data = """try{
        print(JSON.stringify(Reflect.parse(%s)));
    } catch(e) {
        print(JSON.stringify({
            "error":e.toString(),
            "line":e.lineNumber
        }));
    }""" % code

    try:
        process = subprocess.Popen([shell],
                         shell=False,
               stdin=subprocess.PIPE,
              stderr=subprocess.PIPE,
              stdout=subprocess.PIPE)
    except OSError:
        raise OSError("Spidermonkey shell could not be run.")

    data, stderr = process.communicate(data)
    if stderr: raise RuntimeError('Error calling %r: %s' % (cmd, stderr))

    try:
        parsed = json.loads(data, strict=False)
    except Exception as ex:
        # shouldn't happen, obviously, but you never know
        parsed = json.loads('{"error": "failed to parse json", "line": 0}')

    if "error" in parsed:
        if parsed["error"].startswith("ReferenceError"):
            raise RuntimeError("Spidermonkey version too old; "
                               "1.8pre+ required")
        else:
            raise JSReflectException(parsed["error"]).line_num(parsed["line"])

    return parsed
