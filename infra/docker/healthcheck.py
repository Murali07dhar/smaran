#!/usr/bin/env python3
"""Tiny container healthcheck (python:slim has no curl).

  healthcheck.py http://127.0.0.1:8000/openapi.json   -> healthy if the server answers with status < 500
  healthcheck.py 127.0.0.1:8002                       -> healthy if the TCP port accepts connections

Any HTTP status below 500 counts as healthy so it works even when a service has no /health route.
"""
import socket
import sys
import urllib.error
import urllib.request


def check(target: str) -> bool:
    try:
        if target.startswith("http"):
            try:
                urllib.request.urlopen(target, timeout=3)  # noqa: S310 - fixed local URL
            except urllib.error.HTTPError as exc:
                return exc.code < 500
            return True
        host, port = target.rsplit(":", 1)
        socket.create_connection((host, int(port)), timeout=3).close()
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    sys.exit(0 if check(sys.argv[1]) else 1)
