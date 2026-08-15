from __future__ import annotations

import os


class SecretStoreError(RuntimeError):
    pass


class SecretStore:
    """Stores secrets in the OS credential vault; environment variables win."""

    SERVICE_NAME = "jarvis-assistant"
    BRAIN_ACCOUNT = "brain-api-key"

    def get_brain_api_key(self) -> str:
        environment_value = os.environ.get("JARVIS_API_KEY", "").strip()
        if environment_value:
            return environment_value
        try:
            import keyring

            return (keyring.get_password(self.SERVICE_NAME, self.BRAIN_ACCOUNT) or "").strip()
        except Exception:
            return ""

    def has_brain_api_key(self) -> bool:
        return bool(self.get_brain_api_key())

    def set_brain_api_key(self, value: str | None) -> None:
        try:
            import keyring
        except ImportError as exc:
            raise SecretStoreError(
                "缺少 keyring，无法安全保存密钥。可改用 JARVIS_API_KEY 环境变量。"
            ) from exc

        try:
            cleaned = (value or "").strip()
            if cleaned:
                keyring.set_password(self.SERVICE_NAME, self.BRAIN_ACCOUNT, cleaned)
            else:
                try:
                    keyring.delete_password(self.SERVICE_NAME, self.BRAIN_ACCOUNT)
                except keyring.errors.PasswordDeleteError:
                    pass
        except Exception as exc:
            raise SecretStoreError(f"系统凭据库保存失败：{exc}") from exc

