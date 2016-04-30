import json
import jsonrpclib

VALUES = {'Neutral': 0, 'Positive': 1, 'Negative': -1, 'Very Negative': -2, 'Very Positive': 2}

class StanfordNLP:
    def __init__(self, port_number=8080):
        self.server = jsonrpclib.Server("http://localhost:%d" % port_number)

    def parse(self, text):
        return json.loads(self.server.parse(text))
