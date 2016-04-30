import json
import optparse
import os
import re
import sys
import glob
import pexpect
import tempfile
import shutil
from progressbar import ProgressBar, Fraction
from subprocess import call

VERBOSE = False
STATE_START, STATE_TEXT, STATE_WORDS, STATE_TREE, STATE_DEPENDENCY, STATE_COREFERENCE = 0, 1, 2, 3, 4, 5
WORD_PATTERN = re.compile('\[([^\]]+)\]')
CR_PATTERN = re.compile(r"\((\d*),(\d*),\[(\d*),(\d*)\]\) -> \((\d*),(\d*),\[(\d*),(\d*)\]\), that is: \"(.*)\" -> \"(.*)\"")

if os.environ.has_key("CORENLP"):
    DIRECTORY = os.environ["CORENLP"]
else:
    DIRECTORY = "stanford-corenlp-full-2015-04-20"

class bc:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


class ProcessError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class ParserError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class TimeoutError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class OutOfMemoryError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def init_corenlp_command(corenlp_path, memory, properties):
    """
    Checks the location of the jar files.
    Spawns the server as a process.
    """

    jars = ["stanford-corenlp-?.?.?.jar",
            "stanford-corenlp-?.?.?-models.jar",
            "xom.jar",
            "joda-time.jar",
            "jollyday.jar",
            "ejml-?.*.jar", # No idea what this is but it might be sentiment
            "javax.json-api-1.0-sources.jar",
            "javax.json.jar",
            "joda-time-2.1-sources.jar",
            "jollyday-0.4.7-sources.jar",
            "stanford-corenlp-?.?.?-javadoc.jar",
            "stanford-corenlp-?.?.?-sources.jar",
            "xom-1.2.10-src.jar"]

    java_path = "java"
    classname = "edu.stanford.nlp.pipeline.StanfordCoreNLP"

    # include the properties file, so you can change defaults
    # but any changes in output format will break parse_parser_results()
    current_dir_pr = os.path.dirname(os.path.abspath(__file__)) + "/" + properties
    if os.path.exists(properties):
        props = "-props %s" % (properties)
    elif os.path.exists(current_dir_pr):
        props = "-props %s" % (current_dir_pr)
    else:
        raise Exception("Error! Cannot locate: %s" % properties)

    # add and check classpaths
    jars = [corenlp_path + "/" + jar for jar in jars]
    missing = [jar for jar in jars if not glob.glob(jar)]
    if missing:
        raise Exception("Error! Cannot locate: %s" % ', '.join(missing))
    jars = [glob.glob(jar)[0] for jar in jars]

    # add memory limit on JVM
    if memory:
        limit = "-Xmx%s" % memory
    else:
        limit = ""

    print "%s %s -cp %s %s %s" % (java_path, limit, ':'.join(jars), classname, props)
    return "%s %s -cp %s %s %s" % (java_path, limit, ':'.join(jars), classname, props)


def remove_id(word):
    """Removes the numeric suffix from the parsed recognized words: e.g. 'word-2' > 'word' """
    return word.count("-") == 0 and word or word[0:word.rindex("-")]


def parse_bracketed(s):
    '''Parse word features [abc=... def = ...]
    Also manages to parse out features that have XML within them
    '''
    word = None
    attrs = {}
    temp = {}
    # Substitute XML tags, to replace them later
    for i, tag in enumerate(re.findall(r"(<[^<>]+>.*<\/[^<>]+>)", s)):
        temp["^^^%d^^^" % i] = tag
        s = s.replace(tag, "^^^%d^^^" % i)
    # Load key-value pairs, substituting as necessary
    for attr, val in re.findall(r"([^=\s]*)=([^=\s]*)", s):
        if val in temp:
            val = temp[val]
        if attr == 'Text':
            word = val
        else:
            attrs[attr] = val
    return (word, attrs)


def parse_parser_results(text):
    """ This is the nasty bit of code to interact with the command-line
    interface of the CoreNLP tools.  Takes a string of the parser results

    and then returns a Python list of dictionaries, one for each parsed
    sentence.
    """
    results = {"sentences": []}
    state = STATE_START

    if sys.version_info[0] < 3 and isinstance(text, str) or \
            sys.version_info[0] >= 3 and isinstance(text, bytes):
        text = text.decode('utf-8')

    for line in text.split('\n'):
        line = line.strip()

        if line.startswith("Sentence #"):
            index = line.index("sentiment: ")
            length = len("sentiment: ")
            sentiment = line[(index+length): -2]
            sentence = {'sentiment': [], 'words': [], 'parsetree': [], 'dependencies': [], 'indexeddependencies': []}
            sentence['sentiment'] = sentiment
            results["sentences"].append(sentence)
            state = STATE_TEXT

        elif state == STATE_TEXT:
            sentence['text'] = line
            state = STATE_WORDS

        elif state == STATE_WORDS:
            if not line.startswith("[Text="):
                raise ParserError('Parse error. Could not find "[Text=" in: %s' % line)
            for s in WORD_PATTERN.findall(line):
                sentence['words'].append(parse_bracketed(s))
            state = STATE_TREE

        elif state == STATE_TREE:
            if len(line) == 0:
                state = STATE_DEPENDENCY
                sentence['parsetree'] = " ".join(sentence['parsetree'])
            else:
                sentence['parsetree'].append(line)

        elif state == STATE_DEPENDENCY:
            if len(line) == 0:
                state = STATE_COREFERENCE
            else:
                split_entry = re.split("\(|, ", line[:-1])
                if len(split_entry) == 3:
                    rel, left, right = map(lambda x: remove_id(x), split_entry)
                    sentence['dependencies'].append(tuple([rel, left, right]))
                    sentence['indexeddependencies'].append(tuple(split_entry))

        elif state == STATE_COREFERENCE:
            if "Coreference set" in line:
                if 'coref' not in results:
                    results['coref'] = []
                coref_set = []
                results['coref'].append(coref_set)
            else:
                for src_i, src_pos, src_l, src_r, sink_i, sink_pos, sink_l, sink_r, src_word, sink_word in CR_PATTERN.findall(line):
                    src_i, src_pos, src_l, src_r = int(src_i) - 1, int(src_pos) - 1, int(src_l) - 1, int(src_r) - 1
                    sink_i, sink_pos, sink_l, sink_r = int(sink_i) - 1, int(sink_pos) - 1, int(sink_l) - 1, int(sink_r) - 1
                    coref_set.append(((src_word, src_i, src_pos, src_l, src_r), (sink_word, sink_i, sink_pos, sink_l, sink_r)))

    return results

class StanfordCoreNLP:

    """
    Command-line interaction with Stanford's CoreNLP java utilities.
    Can be run as a JSON-RPC server or imported as a module.
    """

    def _spawn_corenlp(self):
        if VERBOSE:
            print "Other verbose entered: "
            print self.start_corenlp
        self.corenlp = pexpect.spawn(self.start_corenlp, timeout=60, maxread=8192, searchwindowsize=80)

        # show progress bar while loading the models
        if VERBOSE:
            print "Verbose entered: "
            widgets = ['Loading Models: ', Fraction()]
            pbar = ProgressBar(widgets=widgets, maxval=5, force_update=True).start()
            # Model timeouts:
            # pos tagger model (~5sec)
            # NER-all classifier (~33sec)
            # NER-muc classifier (~60sec)
            # CoNLL classifier (~50sec)
            # PCFG (~3sec)
            timeouts = [20, 200, 600, 600, 20]
            for i in xrange(5):
                self.corenlp.expect("done.", timeout=timeouts[i])  # Load model
                pbar.update(i + 1)
            self.corenlp.expect("Entering interactive shell.")
            pbar.finish()

        # interactive shell
        self.corenlp.expect("\nNLP> ")

    def __init__(self, corenlp_path=DIRECTORY, memory="3g", properties='default.properties', serving=False):
        """
        Checks the location of the jar files.
        Spawns the server as a process.
        """

        # spawn the server
        self.serving = serving
        xml_dir_server = tempfile.mkdtemp()
        self.start_corenlp = init_corenlp_command(corenlp_path, memory, properties)
        self._spawn_corenlp()

    def close(self, force=True):
        self.corenlp.terminate(force)

    def isalive(self):
        return self.corenlp.isalive()

    def __del__(self):
        # If our child process is still around, kill it
        if self.isalive():
            self.close()

    def _parse(self, text):
        """
        This is the core interaction with the parser.

        It returns a Python data-structure, while the parse()
        function returns a JSON object
        """

        # CoreNLP interactive shell cannot recognize newline
        if '\n' in text or '\r' in text:
            to_send = re.sub("[\r\n]", " ", text).strip()
        else:
            to_send = text

        # clean up anything leftover
        def clean_up():
            while True:
                try:
                    self.corenlp.read_nonblocking(8192, 0.1)
                except pexpect.TIMEOUT:
                    break
        clean_up()

        self.corenlp.sendline(to_send)

        # How much time should we give the parser to parse it?
        # the idea here is that you increase the timeout as a
        # function of the text's length.
        # max_expected_time = max(5.0, 3 + len(to_send) / 5.0)
        max_expected_time = max(300.0, len(to_send) / 3.0)

        # repeated_input = self.corenlp.except("\n")  # confirm it
        t = self.corenlp.expect(["\nNLP> ", pexpect.TIMEOUT, pexpect.EOF,
                                 "\nWARNING: Parsing of sentence failed, possibly because of out of memory."],
                                timeout=max_expected_time)
        incoming = self.corenlp.before
        if t == 1:
            # TIMEOUT, clean up anything left in buffer
            clean_up()
            print >>sys.stderr, {'error': "timed out after %f seconds" % max_expected_time,
                                 'input': to_send,
                                 'output': incoming}
            raise TimeoutError("Timed out after %d seconds" % max_expected_time)
        elif t == 2:
            # EOF, probably crash CoreNLP process
            print >>sys.stderr, {'error': "CoreNLP terminates abnormally while parsing",
                                 'input': to_send,
                                 'output': incoming}
            raise ProcessError("CoreNLP process terminates abnormally while parsing")
        elif t == 3:
            # out of memory
            print >>sys.stderr, {'error': "WARNING: Parsing of sentence failed, possibly because of out of memory.",
                                 'input': to_send,
                                 'output': incoming}
            raise OutOfMemoryError

        if VERBOSE:
            print "%s\n%s" % ('=' * 40, incoming)
        try:
            print incoming
            results = parse_parser_results(incoming)
        except Exception as e:
            if VERBOSE:
                print traceback.format_exc()
            raise e

        return results

    def raw_parse(self, text):
        """
        This function takes a text string, sends it to the Stanford parser,
        reads in the result, parses the results and returns a list
        with one dictionary entry for each parsed sentence.
        """
        try:
            r = self._parse(text)
            return r
        except Exception as e:
            print e  # Should probably log somewhere instead of printing
            self.corenlp.close()
            self._spawn_corenlp()
            if self.serving:  # We don't want to raise the exception when acting as a server
                return []
            raise e

    def parse(self, text):
        """
        This function takes a text string, sends it to the Stanford parser,
        reads in the result, parses the results and returns a list
        with one dictionary entry for each parsed sentence, in JSON format.
        """
        return json.dumps(self.raw_parse(text))


def main():
    """
    The code below starts an JSONRPC server
    """
    from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer
    parser = optparse.OptionParser(usage="%prog [OPTIONS]")
    parser.add_option('-p', '--port', default='8080',
                      help='Port to serve on (default 8080)')
    parser.add_option('-H', '--host', default='127.0.0.1',
                      help='Host to serve on (default localhost; 0.0.0.0 to make public)')
    parser.add_option('-q', '--quiet', action='store_false', default=True, dest='verbose',
                      help="Quiet mode, don't print status msgs to stdout")
    parser.add_option('-S', '--corenlp', default=DIRECTORY,
                      help='Stanford CoreNLP tool directory (default %s)' % DIRECTORY)
    parser.add_option('-P', '--properties', default='default.properties',
                      help='Stanford CoreNLP properties fieles (default: default.properties)')
    options, args = parser.parse_args()
    VERBOSE = options.verbose
    
    try:
        server = SimpleJSONRPCServer((options.host, int(options.port)))

        nlp = StanfordCoreNLP(options.corenlp, properties=options.properties, serving=True)
        server.register_function(nlp.parse)
        server.register_function(nlp.raw_parse)

        print 'Serving on http://%s:%s' % (options.host, options.port)
        # server.serve()
        server.serve_forever()
    except KeyboardInterrupt:
        print >>sys.stderr, "Bye."
        exit()

if __name__ == '__main__':
    main()
