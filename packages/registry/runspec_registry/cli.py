"""
cli.py — Entry point for the runspec-registry server.

Usage:
  runspec-registry [options]

Options:
  --host TEXT         Bind host (default: 0.0.0.0)
  --port INT          Bind port (default: 8765)
  --api-key TEXT      API key for write endpoints (optional)
  --ssl-keyfile PATH  Path to SSL private key file
  --ssl-certfile PATH Path to SSL certificate file
  --purge-interval INT  Seconds between stale-instance purge runs (default: 60)
  --reload            Enable auto-reload (dev mode)
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runspec-registry", description="runspec registry server")
    p.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    p.add_argument("--api-key", default=None, help="API key for write endpoint authentication")
    p.add_argument("--ssl-keyfile", default=None, help="Path to SSL private key")
    p.add_argument("--ssl-certfile", default=None, help="Path to SSL certificate")
    p.add_argument("--purge-interval", type=int, default=60, help="Seconds between stale-instance purge runs (default: 60)")
    p.add_argument("--reload", action="store_true", help="Enable auto-reload (development only)")
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        sys.stderr.write("runspec-registry: uvicorn is required. Install with: pip install runspec-registry\n")
        sys.exit(1)

    # Build app factory string for reload mode, or instance for direct mode
    api_key: str | None = args.api_key
    purge_interval: int = args.purge_interval

    if args.reload:
        # uvicorn reload requires an import string
        import os

        os.environ["RUNSPEC_REGISTRY_API_KEY"] = api_key or ""
        os.environ["RUNSPEC_REGISTRY_PURGE_INTERVAL"] = str(purge_interval)
        app_str = "runspec_registry.app:_reload_app"
        uvicorn.run(
            app_str,
            host=args.host,
            port=args.port,
            reload=True,
            ssl_keyfile=args.ssl_keyfile,
            ssl_certfile=args.ssl_certfile,
        )
    else:
        from .app import create_app

        app = create_app(api_key=api_key, purge_interval=purge_interval)
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            ssl_keyfile=args.ssl_keyfile,
            ssl_certfile=args.ssl_certfile,
        )
