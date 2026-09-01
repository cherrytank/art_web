"""Build and serve the site locally for preview."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import build_site


def main() -> None:
    parser = argparse.ArgumentParser(description="重建並在本機預覽網站")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    build_site.build()
    handler = partial(SimpleHTTPRequestHandler, directory=str(build_site.DIST))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Preview: http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview stopped.")


if __name__ == "__main__":
    main()
