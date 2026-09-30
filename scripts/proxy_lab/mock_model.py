"""Offline OpenAI-compatible HTTPS fixture. No real credentials or model calls."""
import argparse
import json
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        data = b'{"status":"ok","service":"fake-model"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        base = {"id": "chatcmpl-local-lab", "created": int(time.time()), "model": "lab-model"}
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for piece in ("LOCAL_", "MODEL_", "OK"):
                time.sleep(0.35)
                item = dict(base, object="chat.completion.chunk", choices=[{
                    "index": 0, "delta": {"content": piece}, "finish_reason": None}])
                self.wfile.write(("data: " + json.dumps(item) + "\n\n").encode())
                self.wfile.flush()
            item = dict(base, object="chat.completion.chunk", choices=[{
                "index": 0, "delta": {}, "finish_reason": "stop"}])
            self.wfile.write(("data: " + json.dumps(item) + "\n\ndata: [DONE]\n\n").encode())
            self.wfile.flush()
            self.close_connection = True
        else:
            data = json.dumps(dict(base, object="chat.completion", choices=[{
                "index": 0, "message": {"role": "assistant", "content": "LOCAL_MODEL_OK"},
                "finish_reason": "stop"}], usage={"prompt_tokens": 4, "completion_tokens": 3,
                "total_tokens": 7})).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(args.runtime / "certs/model-cert.pem", args.runtime / "certs/model-key.pem")
    server = ThreadingHTTPServer((args.host, 19443), Handler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
