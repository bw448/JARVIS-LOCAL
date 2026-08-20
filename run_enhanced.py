"""
Run JARVIS LOCAL Enhanced v1.1.0
集成 Memory、Skills、Web Search、Document Processing
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from jarvis.app_enhanced import run_enhanced_server
from jarvis.config import SettingsStore, default_data_dir


def main():
    parser = argparse.ArgumentParser(description="JARVIS LOCAL Enhanced")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--data-dir", type=str, help="Data directory")
    args = parser.parse_args()

    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║           JARVIS LOCAL Enhanced v1.1.0                   ║
    ║  ─────────────────────────────────────────────────────── ║
    ║  ✨ Memory System - 记忆对话和重要信息                   ║
    ║  🔧 Skills System - 专业技能增强                         ║
    ║  🔍 Web Search - 互联网搜索能力                          ║
    ║  📄 Document Processing - 文档处理能力                    ║
    ║  🎤 Voice System - 本地语音识别和合成                     ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    data_dir = Path(args.data_dir) if args.data_dir else None
    
    print(f"[JARVIS] Starting enhanced server on http://{args.host}:{args.port}")
    print(f"[JARVIS] Data directory: {data_dir or default_data_dir() / 'jarvis_data'}")
    print(f"[JARVIS] Press Ctrl+C to stop")
    print()

    try:
        run_enhanced_server(
            host=args.host,
            port=args.port,
        )
    except KeyboardInterrupt:
        print("\n[JARVIS] Server stopped.")
    except Exception as e:
        print(f"\n[JARVIS] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
