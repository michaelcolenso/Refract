#!/usr/bin/env python3
"""
REFRACT local dev runner.
Watches inbox/, runs the pipeline when new images arrive, and serves site/public.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from pipeline import RefractPipeline


def start_server(repo_root: Path, port: int, verbose: bool) -> Optional[subprocess.Popen]:
    serve_path = repo_root / "scripts" / "serve.py"
    if not serve_path.exists():
        print(f"Error: {serve_path} not found.", file=sys.stderr)
        return None

    cmd = [sys.executable, str(serve_path), "--port", str(port)]
    if verbose:
        cmd.append("--verbose")

    return subprocess.Popen(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the local pipeline and dev server."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the local server (default: 8000)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Seconds between inbox checks (default: 5)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run the pipeline once and exit (no watch loop)",
    )
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Do not start the local server",
    )
    parser.add_argument(
        "--verbose-serve",
        action="store_true",
        help="Show all HTTP requests in server logs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze only (no edits, archive, or site rebuild)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    load_dotenv(repo_root / ".env")

    try:
        pipeline = RefractPipeline(repo_root, dry_run=args.dry_run)
    except Exception as exc:
        print(f"Failed to initialize pipeline: {exc}", file=sys.stderr)
        return 1

    server_proc = None
    if not args.no_serve:
        server_proc = start_server(repo_root, args.port, args.verbose_serve)
        if server_proc:
            print(f"Server running at http://localhost:{args.port}")

    try:
        if args.once:
            if pipeline.get_new_images():
                pipeline.run()
            else:
                print("No new images found in inbox/.")
        else:
            print(f"Watching inbox/ every {args.interval}s. Press Ctrl+C to stop.")
            while True:
                if pipeline.get_new_images():
                    pipeline.run()
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping dev runner.")
    finally:
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
