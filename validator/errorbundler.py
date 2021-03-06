import json
import uuid
from StringIO import StringIO

from contextgenerator import ContextGenerator
from outputhandlers.shellcolors import OutputHandler
from textfilter import filter_ascii

class ErrorBundle(object):
    """This class does all sorts of cool things. It gets passed around
    from test to test and collects up all the errors like the candy man
    'separating the sorrow and collecting up all the cream.' It's
    borderline magical."""
    
    def __init__(self, determined=True, listed=True):
        
        self.handler = None

        self.errors = []
        self.warnings = []
        self.notices = []
        self.message_tree = {}

        self.tier = 1
        
        self.metadata = {}
        self.determined = determined
        
        self.subpackages = []
        self.package_stack = []
        
        self.detected_type = 0
        self.resources = {}
        self.pushable_resources = {}
        self.reject = False
        self.unfinished = False
        
        if listed:
            self.resources["listed"] = True

    def error(self, err_id, error,
              description='', filename='', line=0, column=0, context=None,
              tier=None):
        "Stores an error message for the validation process"
        self._save_message(self.errors,
                           "errors",
                           {"id": err_id,
                            "message": error,
                            "description": description,
                            "file": filename,
                            "line": line,
                            "column": column,
                            "tier": tier},
                           context=context)
        return self
        
    def warning(self, err_id, warning,
                description='', filename='', line=0, column=0, context=None,
                tier=None):
        "Stores a warning message for the validation process"
        self._save_message(self.warnings,
                           "warnings",
                           {"id": err_id,
                            "message": warning,
                            "description": description,
                            "file": filename,
                            "line": line,
                            "column": column,
                            "tier": tier},
                           context=context)
        return self

    # NOTE : This function WILL NOT support contexts since it's deprecated.
    def info(self, err_id, info, description="", filename="", line=0):
        "An alias for notice"
        self.notice(err_id, info, description, filename, line)

    def notice(self, err_id, notice,
               description="", filename="", line=0, column=0, context=None,
               tier=None):
        "Stores an informational message about the validation"
        self._save_message(self.notices,
                           "notices",
                           {"id": err_id,
                            "message": notice,
                            "description": description,
                            "file": filename,
                            "line": line,
                            "column": column,
                            "tier": tier},
                           context=context)
        return self
        
    def _save_message(self, stack, type_, message, context=None):
        "Stores a message in the appropriate message stack."
        
        uid = uuid.uuid4().hex
        
        message["uid"] = uid

        # Get the context for the message (if there's a context available)
        if context is not None:
            if isinstance(context, tuple):
                message["context"] = context
            else:
                message["context"] = \
                            context.get_context(line=message["line"],
                                                column=message["column"])
        else:
            message["context"] = None
        
        message["message"] = filter_ascii(message["message"])
        message["description"] = filter_ascii(message["description"])
        
        stack.append(message)
        
        # Mark the tier that the error occurred at
        if message["tier"] is None:
            message["tier"] = self.tier

        if message["id"]:
            tree = self.message_tree
            last_id = None
            for eid in message["id"]:
                if last_id is not None:
                    tree = tree[last_id]
                if eid not in tree:
                    tree[eid] = {"__errors": 0,
                                 "__warnings": 0,
                                 "__notices": 0,
                                 "__messages": []}
                tree[eid]["__%s" % type_] += 1
                last_id = eid
        
            tree[last_id]['__messages'].append(uid)
        
    def set_type(self, type_):
        "Stores the type of addon we're scanning"
        self.detected_type = type_
    
    def failed(self, fail_on_warnings=True):
        """Returns a boolean value describing whether the validation
        succeeded or not."""
        
        return self.errors or (fail_on_warnings and self.warnings)
        
    def get_resource(self, name):
        "Retrieves an object that has been stored by another test."
        
        if name in self.resources:
            return self.resources[name]
        elif name in self.pushable_resources:
            return self.pushable_resources[name]
        else:
            return False
        
    def save_resource(self, name, resource, pushable=False):
        "Saves an object such that it can be used by other tests."
        
        if pushable:
            self.pushable_resources[name] = resource
        else:
            self.resources[name] = resource
        
    def is_nested_package(self):
        "Returns whether the current package is within a PACKAGE_MULTI"
        
        return bool(self.package_stack)
    
    def push_state(self, new_file=""):
        "Saves the current error state to parse subpackages"
        
        self.subpackages.append({"errors": self.errors,
                                 "warnings": self.warnings,
                                 "notices": self.notices,
                                 "detected_type": self.detected_type,
                                 "message_tree": self.message_tree,
                                 "resources": self.pushable_resources,
                                 "metadata": self.metadata})
        
        self.errors = []
        self.warnings = []
        self.notices = []
        self.message_tree = {}
        self.pushable_resources = {}
        self.metadata = {}
        
        self.package_stack.append(new_file)
    
    def pop_state(self):
        "Retrieves the last saved state and restores it."
        
        # Save a copy of the current state.
        state = self.subpackages.pop()
        errors = self.errors
        warnings = self.warnings
        notices = self.notices
        # We only rebuild message_tree anyway. No need to restore.
        
        # Copy the existing state back into place
        self.errors = state["errors"]
        self.warnings = state["warnings"]
        self.notices = state["notices"]
        self.detected_type = state["detected_type"]
        self.message_tree = state["message_tree"]
        self.pushable_resources = state["resources"]
        self.metadata = state["metadata"]
        
        name = self.package_stack.pop()
        
        self._merge_messages(errors, self.error, name)
        self._merge_messages(warnings, self.warning, name)
        self._merge_messages(notices, self.notice, name)
        
    
    def _merge_messages(self, messages, callback, name):
        "Merges a stack of messages into another stack of messages"
        
        # Overlay the popped warnings onto the existing ones.
        for message in messages:
            trace = [name]
            # If there are sub-sub-packages, they'll be in a list.
            if isinstance(message["file"], list):
                trace.extend(message["file"])
            else:
                trace.append(message["file"])
            
            # Write the errors with the file structure delimited by
            # right carets.
            callback(message["id"],
                     message["message"],
                     description=message["description"],
                     filename=trace,
                     line=message["line"],
                     column=message["column"],
                     context=message["context"],
                     tier=message["tier"])
    
    
    def _clean_description(self, message, json=False):
        "Cleans all the nasty whitespace from the descriptions."
        
        output = self._clean_message(message["description"], json)
        message["description"] = output
        
    def _clean_message(self, desc, json=False):
        "Cleans all the nasty whitespace from a string."
        
        output = []
        
        if not isinstance(desc, list):
            lines = desc.splitlines()
            for line in lines:
                output.append(line.strip())
            return " ".join(output)
        else:
            for line in desc:
                output.append(self._clean_message(line, json))
            if json:
                return output
            else:
                return "\n".join(output)
    
    def render_json(self, cluster=False):
        "Returns a JSON summary of the validation operation."
        
        types = {0: "unknown",
                 1: "extension",
                 2: "theme",
                 3: "dictionary",
                 4: "langpack",
                 5: "search"}
        output = {"detected_type": types[self.detected_type],
                  "ending_tier": self.tier,
                  "success": not self.failed(),
                  "rejected": self.reject,
                  "messages":[],
                  "errors": len(self.errors),
                  "warnings": len(self.warnings),
                  "notices": len(self.notices),
                  "message_tree": self.message_tree,
                  "metadata": self.metadata}
        
        messages = output["messages"]
        
        # Copy messages to the JSON output
        for error in self.errors:
            error["type"] = "error"
            self._clean_description(error, True)
            messages.append(error)
            
        for warning in self.warnings:
            warning["type"] = "warning"
            self._clean_description(warning, True)
            messages.append(warning)
            
        for notice in self.notices:
            notice["type"] = "notice"
            self._clean_description(notice, True)
            messages.append(notice)
        
        # Output the JSON.
        return json.dumps(output)
    
    def print_summary(self, verbose=False, no_color=False):
        "Prints a summary of the validation process so far."
        
        types = {0: "Unknown",
                 1: "Extension/Multi-Extension",
                 2: "Theme",
                 3: "Dictionary",
                 4: "Language Pack",
                 5: "Search Provider",
                 7: "Subpackage"}
        detected_type = types[self.detected_type]
        
        buffer = StringIO()
        self.handler = OutputHandler(buffer, no_color)

        # Make a neat little printout.
        self.handler.write("\n<<GREEN>>Summary:") \
            .write("-" * 30) \
            .write("Detected type: <<BLUE>>%s" % detected_type) \
            .write("-" * 30)
        
        if self.failed():
            self.handler.write("<<BLUE>>Test failed! Errors:")
            
            # Print out all the errors/warnings:
            for error in self.errors:
                self._print_message("<<RED>>Error:<<NORMAL>>\t",
                                    error, verbose)
            for warning in self.warnings:
                self._print_message("<<YELLOW>>Warning:<<NORMAL>> ",
                                    warning, verbose)
            
            
            # Awwww... have some self esteem!
            if self.reject:
                self.handler.write("Extension Rejected")
            
        else:
            self.handler.write("<<GREEN>>All tests succeeded!")
            
        
        if self.notices:
            for notice in self.notices:
                self._print_message(prefix="<<WHITE>>Notice:<<NORMAL>>\t",
                                    message=notice,
                                    verbose=verbose)
        
        self.handler.write("\n")
        if self.unfinished:
            self.handler.write("<<RED>>Validation terminated early")
            self.handler.write("Errors during validation are preventing"
                               "the validation proecss from completing.")
            self.handler.write("Use the <<YELLOW>>--determined<<NORMAL>> "
                               "flag to ignore these errors.")
            self.handler.write("\n")

        return buffer.getvalue()
        
    def _print_message(self, prefix, message, verbose=True):
        "Prints a message and takes care of all sorts of nasty code"
        
        # Load up the standard output.
        output = ["\n",
                  prefix,
                  self._clean_message([message["message"]]),
                  "\n"]
        
        # We have some extra stuff for verbose mode.
        if verbose:
            verbose_output = []
            
            # Detailed problem description.
            if message["description"]:
                # These are dirty, so strip out whitespace and concat.
                verbose_output.append(
                            self._clean_message(message["description"]))
            
            # Show the user what tier we're on
            verbose_output.append("\tTier:\t%d" % message["tier"])

            # If file information is available, output that as well.
            files = message["file"]
            if files is not None and files != "":
                fmsg = "\tFile:\t%s"
                
                # Nested files (subpackes) are stored in a list.
                if type(files) is list:
                    if files[-1] == "":
                        files[-1] = "(none)"
                    verbose_output.append(fmsg % ' > '.join(files))
                else:
                    verbose_output.append(fmsg % files)
            
            # If there is a line number, that gets put on the end.
            if message["line"]:
                verbose_output.append("\tLine:\t%s" % message["line"])
            if message["column"] and message["column"] != 0:
                verbose_output.append("\tColumn:\t%d" % message["column"])

            if "context" in message and message["context"]:
                verbose_output.append("\tContext:")
                verbose_output.extend([("\t>\t%s" % x
                                        if x is not None
                                        else "\t>" + ("-" * 20))
                                       for x
                                       in message["context"]])

            # Stick it in with the standard items.
            output.append("\n")
            output.append("\n".join(verbose_output))
        
        # Send the final output to the handler to be rendered.
        self.handler.write(''.join(output))
        
