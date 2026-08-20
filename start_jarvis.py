"""
启动 JARVIS LOCAL - 使用原始app.py（完整语音功能）
"""

import sys
import argparse
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from jarvis.app import create_server


def main():
    parser = argparse.ArgumentParser(description="JARVIS LOCAL v1.1.0")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║           JARVIS LOCAL v1.1.0                            ║
    ║  ─────────────────────────────────────────────────────── ║
    ║  🎤 语音识别/合成 - 本地运行                             ║
    ║  🧠 AI 对话 - OpenAI 兼容接口                            ║
    ║  🔧 完整功能 - 语音模式、设置等                          ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    server = None
    last_error = None
    
    for candidate_port in range(args.port, min(args.port + 20, 65536)):
        try:
            server = create_server(args.host, candidate_port)
            break
        except OSError as exc:
            last_error = exc
    
    if server is None:
        print(f"无法启动服务: {last_error}")
        sys.exit(1)
    
    server.application.start_prewarm()
    host, port = server.server_address[:2]
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}/"
    
    print(f"[JARVIS] 已启动: {url}")
    print(f"[JARVIS] 按 Ctrl+C 退出")
    
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n[JARVIS] 正在退出...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
