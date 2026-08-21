#!/usr/bin/env python3
"""JARVIS LOCAL 启动入口"""

import sys
from pathlib import Path

# 确保当前目录在路径中
sys.path.insert(0, str(Path(__file__).parent))


def main():
    # 检查是否首次运行
    try:
        from jarvis.first_run import check_tts_model, check_stt_model, setup_first_run
        
        if not check_tts_model() or not check_stt_model():
            print("\n检测到语音模型缺失，需要下载才能使用完整功能")
            choice = input("是否现在下载？(y/n): ").strip().lower()
            if choice == 'y':
                setup_first_run()
            else:
                print("跳过下载，语音功能将受限\n")
    except Exception as e:
        print(f"首次运行检查失败: {e}")
    
    # 启动应用
    try:
        from jarvis.app import JarvisApplication
        from jarvis.config import SettingsStore
        
        store = SettingsStore()
        app = JarvisApplication(settings_store=store)
        
        print(f"\n{'='*50}")
        print(f"JARVIS LOCAL v{app.settings.identity.assistant_name}")
        print(f"{'='*50}")
        print(f"访问 http://127.0.0.1:8080 开始使用")
        print(f"{'='*50}\n")
        
        app.run()
    except KeyboardInterrupt:
        print("\n再见！")
    except Exception as e:
        print(f"\n启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
