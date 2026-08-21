"""
JARVIS Settings Manager - 配置管理工具

提供简单的接口来管理 JARVIS 配置，包括：
- API Key 设置
- 模型选择
- DSH 开关
- 配置持久化
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .config import Settings, SettingsStore, default_data_dir


class SettingsManager:
    """JARVIS 配置管理器"""
    
    def __init__(self, settings_path: Optional[Path] = None):
        self._store = SettingsStore(settings_path)
        self._settings = self._store.load()
    
    @property
    def settings(self) -> Settings:
        return self._settings
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前配置状态"""
        return {
            "dsh": {
                "enabled": self._settings.dsh.enabled,
                "model": self._settings.dsh.model,
                "api_key_configured": bool(self._settings.dsh.api_key),
                "base_url": self._settings.dsh.base_url or "默认 (api.deepseek.com)",
                "fallback": self._settings.dsh.fallback_to_openai,
            },
            "brain": {
                "provider": self._settings.brain.provider,
                "model": self._settings.brain.model,
            },
            "identity": {
                "assistant_name": self._settings.identity.assistant_name,
                "owner_name": self._settings.identity.owner_name,
            }
        }
    
    def set_dsh_api_key(self, api_key: str) -> bool:
        """设置 DeepSeek API Key"""
        try:
            # 更新配置
            config_dict = self._settings.to_dict()
            config_dict["dsh"]["api_key"] = api_key
            self._settings = Settings.from_mapping(config_dict)
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"设置 API Key 失败: {e}")
            return False
    
    def set_dsh_enabled(self, enabled: bool) -> bool:
        """启用/禁用 DeepSeek Harness"""
        try:
            config_dict = self._settings.to_dict()
            config_dict["dsh"]["enabled"] = enabled
            self._settings = Settings.from_mapping(config_dict)
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"设置 DSH 开关失败: {e}")
            return False
    
    def set_dsh_model(self, model: str) -> bool:
        """设置 DSH 模型"""
        try:
            config_dict = self._settings.to_dict()
            config_dict["dsh"]["model"] = model
            self._settings = Settings.from_mapping(config_dict)
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"设置模型失败: {e}")
            return False
    
    def set_dsh_base_url(self, base_url: str) -> bool:
        """设置 DSH Base URL"""
        try:
            config_dict = self._settings.to_dict()
            config_dict["dsh"]["base_url"] = base_url
            self._settings = Settings.from_mapping(config_dict)
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"设置 Base URL 失败: {e}")
            return False
    
    def set_assistant_name(self, name: str) -> bool:
        """设置助手名称"""
        try:
            config_dict = self._settings.to_dict()
            config_dict["identity"]["assistant_name"] = name
            self._settings = Settings.from_mapping(config_dict)
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"设置助手名称失败: {e}")
            return False
    
    def set_owner_name(self, name: str) -> bool:
        """设置主人称呼"""
        try:
            config_dict = self._settings.to_dict()
            config_dict["identity"]["owner_name"] = name
            self._settings = Settings.from_mapping(config_dict)
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"设置主人称呼失败: {e}")
            return False
    
    def reset_to_defaults(self) -> bool:
        """重置为默认配置"""
        try:
            self._settings = Settings()
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"重置配置失败: {e}")
            return False
    
    def export_config(self, path: Path) -> bool:
        """导出配置到文件"""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._settings.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出配置失败: {e}")
            return False
    
    def import_config(self, path: Path) -> bool:
        """从文件导入配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            self._settings = Settings.from_mapping(config_dict)
            self._store.save(self._settings)
            return True
        except Exception as e:
            print(f"导入配置失败: {e}")
            return False


def interactive_setup():
    """交互式配置向导"""
    print("\n" + "=" * 50)
    print("JARVIS 配置向导")
    print("=" * 50)
    
    manager = SettingsManager()
    status = manager.get_status()
    
    print(f"\n当前配置:")
    print(f"  助手名称: {status['identity']['assistant_name']}")
    print(f"  主人称呼: {status['identity']['owner_name']}")
    print(f"  DSH 状态: {'启用' if status['dsh']['enabled'] else '禁用'}")
    print(f"  DSH 模型: {status['dsh']['model']}")
    print(f"  API Key: {'已配置' if status['dsh']['api_key_configured'] else '未配置'}")
    
    print("\n" + "-" * 50)
    print("请选择操作:")
    print("  1. 设置 DeepSeek API Key")
    print("  2. 设置助手名称")
    print("  3. 设置主人称呼")
    print("  4. 切换 DSH 启用/禁用")
    print("  5. 更改 DSH 模型")
    print("  6. 重置为默认配置")
    print("  0. 退出")
    
    while True:
        choice = input("\n请输入选项 (0-6): ").strip()
        
        if choice == "0":
            print("配置完成！")
            break
        elif choice == "1":
            api_key = input("请输入 DeepSeek API Key: ").strip()
            if api_key:
                if manager.set_dsh_api_key(api_key):
                    print("✓ API Key 已保存")
                else:
                    print("✗ 保存失败")
        elif choice == "2":
            name = input("请输入助手名称 (当前: {}): ".format(status['identity']['assistant_name'])).strip()
            if name:
                if manager.set_assistant_name(name):
                    print("✓ 助手名称已更新")
        elif choice == "3":
            name = input("请输入主人称呼 (当前: {}): ".format(status['identity']['owner_name'])).strip()
            if name:
                if manager.set_owner_name(name):
                    print("✓ 主人称呼已更新")
        elif choice == "4":
            current = status['dsh']['enabled']
            new_state = not current
            if manager.set_dsh_enabled(new_state):
                print(f"✓ DSH 已{'启用' if new_state else '禁用'}")
        elif choice == "5":
            model = input("请输入模型名称 (当前: {}): ".format(status['dsh']['model'])).strip()
            if model:
                if manager.set_dsh_model(model):
                    print("✓ 模型已更新")
        elif choice == "6":
            confirm = input("确定要重置为默认配置吗？(y/n): ").strip().lower()
            if confirm == 'y':
                if manager.reset_to_defaults():
                    print("✓ 已重置为默认配置")
        else:
            print("无效选项，请重新输入")


if __name__ == "__main__":
    interactive_setup()
