from __future__ import annotations

import argparse
import os
import threading
import webbrowser

from jarvis.app import create_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the JARVIS LOCAL assistant")
    parser.add_argument("--host", default=os.environ.get("JARVIS_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("JARVIS_PORT", "8765"))
    )
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = None
    last_error: OSError | None = None
    for candidate_port in range(args.port, min(args.port + 20, 65_536)):
        try:
            server = create_server(args.host, candidate_port)
            break
        except OSError as exc:
            last_error = exc
    if server is None:
        raise SystemExit(f"无法启动本地服务：{last_error}")
    server.application.start_prewarm()

    host, port = server.server_address[:2]
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}/"
    print(f"JARVIS LOCAL 已启动：{url}")
    print("按 Ctrl+C 退出。对话正文默认不写入日志。")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nJARVIS LOCAL 正在退出…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
