"""
JARVIS Startup Module - 启动流程管理
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Tuple

from .config import Settings, SettingsStore
from .brain import OpenAICompatibleBrain
from .brain_deepseek import HybridBrain, DSHBrainConfig, DSH_AVAILABLE


class StartupResult:
    def __init__(self):
        self.success = False
        self.warnings = []
        self.errors = []
        self.status = {}
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def add_error(self, msg: str):
        self.errors.append(msg)


def check_models_status() -> Dict[str, bool]:
    """检查模型状态"""
    try:
        from .model_downloader import check_models
        return check_models()
    except Exception:
        return {}


def startup_check(skip_model_check: bool = False) -> StartupResult:
    """执行启动检查"""
    result = StartupResult()
    
    # 加载配置
    store = SettingsStore()
    settings = store.load()
    
    # 检查 DSH 配置
    if settings.dsh.enabled:
        if not DSH_AVAILABLE:
            result.add_warning("DeepSeek Harness SDK 未安装，使用 OpenAI 兼容模式")
        if not settings.dsh.api_key:
            result.add_warning("未配置 DeepSeek API Key")
    
    # 检查模型
    if not skip_model_check:
        model_status = check_models_status()
        if model_status:
            missing = [k for k, v in model_status.items() if not v]
            if missing:
                result.add_warning(f"缺失语音模型: {', '.join(missing)}")
                result.status["missing_models"] = missing
    
    # 初始化大脑
    try:
        dsh_config = DSHBrainConfig(
            enabled=settings.dsh.enabled,
            model=settings.dsh.model,
            provider=settings.dsh.provider,
            max_tokens=settings.dsh.max_tokens,
            runtime_bin=settings.dsh.runtime_bin or None,
            session_root=settings.dsh.session_root or None,
            cordis_config=settings.dsh.cordis_config or None,
            base_url=settings.dsh.base_url or None,
            api_key=settings.dsh.api_key or None,
            request_timeout=settings.dsh.request_timeout,
            shutdown_timeout=settings.dsh.shutdown_timeout,
            fallback_to_openai=settings.dsh.fallback_to_openai,
            env_overrides=settings.dsh.env_overrides,
        )
        brain = HybridBrain(OpenAICompatibleBrain(), dsh_config)
        result.status["brain"] = {
            "active": brain.active_brain,
            "dsh_available": brain._dsh_brain.is_available if brain._dsh_brain else False,
        }
        result.success = True
    except Exception as e:
        result.add_error(f"大脑初始化失败: {e}")
    
    result.status["settings"] = {
        "dsh_enabled": settings.dsh.enabled,
        "dsh_model": settings.dsh.model,
        "api_key_configured": bool(settings.dsh.api_key),
    }
    
    return result


def print_startup_report(result: StartupResult):
    """打印启动报告"""
    print("\n" + "=" * 50)
    print("JARVIS 启动检查")
    print("=" * 50)
    
    if result.success:
        print("\n✓ 启动检查通过")
    
    if result.warnings:
        print("\n⚠️  警告:")
        for w in result.warnings:
            print(f"  - {w}")
    
    if result.errors:
        print("\n❌ 错误:")
        for e in result.errors:
            print(f"  - {e}")
    
    if result.status:
        print("\n📊 状态:")
        brain_info = result.status.get("brain", {})
        print(f"  活跃大脑: {brain_info.get('active', '未知')}")
        print(f"  DSH 可用: {brain_info.get('dsh_available', False)}")


if __name__ == "__main__":
    result = startup_check()
    print_startup_report(result)
