#!/usr/bin/env python3
"""
REFRACT Local Development Server
Simple HTTP server for previewing the generated site.
"""

import os
import sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import argparse


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    """HTTP handler that suppresses routine request logging."""

    def log_message(self, format, *args):
        # Only log errors (non-2xx status codes)
        if len(args) >= 2 and isinstance(args[1], str):
            status = args[1].split()[0] if args[1] else ""
            if status.startswith('2') or status.startswith('3'):
                return
        super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(
        description='Local development server for REFRACT site'
    )
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=8000,
        help='Port to serve on (default: 8000)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show all HTTP requests in log'
    )
    args = parser.parse_args()

    # Find site/public directory
    repo_root = Path(__file__).parent.parent
    public_dir = repo_root / 'site' / 'public'

    if not public_dir.exists():
        print(f"Error: Site directory not found: {public_dir}")
        print("Run 'python scripts/generator.py build' first to generate the site.")
        sys.exit(1)

    # Change to public directory
    os.chdir(public_dir)

    # Choose handler based on verbosity
    handler = SimpleHTTPRequestHandler if args.verbose else QuietHTTPRequestHandler

    # Create and start server
    server = HTTPServer(('localhost', args.port), handler)

    print(f"REFRACT Development Server")
    print(f"Serving: {public_dir}")
    print(f"URL: http://localhost:{args.port}")
    print(f"Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)


if __name__ == '__main__':
    main()
