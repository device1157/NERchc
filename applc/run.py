from __future__ import annotations

import argparse
import os
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ming Shilu historical event platform.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8788")), type=int)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser window.")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        webbrowser.open(url)
    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
