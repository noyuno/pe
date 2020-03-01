from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import asyncio
import sys
import socket
from urllib.parse import urlparse
import os

def makeAPIHandler(queue, logger, token):
    class APIHandler(BaseHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super(APIHandler, self).__init__(*args, **kwargs)

        def do_GET(self):
            parsed_path = urlparse(self.path).path
            if parsed_path == "/":
                self.send_response(200)
                self.send_header('content-type', 'text')
                self.end_headers()
                self.wfile.write('room\nhello'.encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('content-type', 'text')
                self.end_headers()
                self.wfile.write('room\n404 not found'.encode('utf-8'))

        def do_POST(self):
            res = { 'status': 0, 'type': 'none', 'message': 'none' }
            got = { }
            try:
                s = self.rfile.read(int(self.headers.get('content-length'))).decode('utf-8')
                got = json.loads(s)
                if got['token'] is not None and got['token'] == token:
                    self.queue.put(got)
                    res = { 'status': 200 }
                else:
                    res = { 'status': 403 }
            except Exception as e:
                res = { 'status': 500 }
                self.logger.exception('APIHandler.do_POST()', stack_info=True)

            self.send_response(res['status'])
            self.send_header('content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
    ret = APIHandler
    ret.queue = queue
    ret.logger = logger
    return ret

class API():
    def __init__(self, loop, queue, logger, token):
        self.loop = loop
        self.queue = queue
        self.logger = logger
        self.token = token

    def run(self):
        asyncio.set_event_loop(self.loop)
        handler = makeAPIHandler(self.queue, self.logger, self.token)
        port = 80
        try:
            port = int(os.environ.get('PORT'))
        except:
            pass
        if port is None:
            port = 80
        server = HTTPServer(('', port), handler)
        self.logger.debug('listen api at {0}:{1}'.format(socket.gethostbyname_ex(socket.gethostname()), port))
        server.serve_forever()

