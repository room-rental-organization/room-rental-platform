"""Local-only SMTP capture for browser tests. Never runs in the deployed artifact."""
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socketserver
from threading import Lock, Thread

messages: list[dict] = []
lock = Lock()


class SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'220 localhost test mail\r\n')
        while line := self.rfile.readline():
            command = line.decode('ascii', errors='ignore').strip().upper()
            if command.startswith(('EHLO', 'HELO')):
                self.wfile.write(b'250 localhost\r\n')
            elif command == 'DATA':
                self.wfile.write(b'354 End data with dot\r\n')
                chunks = []
                while (part := self.rfile.readline()) not in {b'.\r\n', b''}:
                    chunks.append(part[1:] if part.startswith(b'..') else part)
                message = BytesParser(policy=policy.default).parsebytes(b''.join(chunks))
                with lock:
                    messages.append({'to': str(message['To']), 'subject': str(message['Subject']),
                                     'body': message.get_body(preferencelist=('plain',)).get_content()})
                self.wfile.write(b'250 Captured\r\n')
            elif command == 'QUIT':
                self.wfile.write(b'221 Bye\r\n')
                return
            else:
                self.wfile.write(b'250 OK\r\n')


class HTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            body = json.dumps(messages if self.path == '/messages' else {'status': 'ok'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    with socketserver.ThreadingTCPServer(('127.0.0.1', 8025), SMTPHandler) as smtp:
        Thread(target=smtp.serve_forever, daemon=True).start()
        ThreadingHTTPServer(('127.0.0.1', 8026), HTTPHandler).serve_forever()
