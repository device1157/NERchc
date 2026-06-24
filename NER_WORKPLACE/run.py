from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动明实录目标蒸馏 NER 工作台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    return parser.parse_args()


def open_browser_later(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    args = parse_args()
    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()
    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()

