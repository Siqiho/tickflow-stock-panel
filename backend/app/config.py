"""全局配置 — 从环境变量 / .env 读取。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 运行环境检测 ──────────────────────────────────────────
# PyInstaller 打包后: __file__ 指向临时解压目录 _MEIPASS, 不能作为路径基准。
# 此时:
#   - 只读资源 (tiers.yaml / 前端 dist) 放在 _MEIPASS 内
#   - 可写用户数据 (data_dir) 放在可执行文件旁的用户目录
# 非 frozen 模式 (开发/Docker): 保持原有 __file__ 推导, 行为完全不变。
_IS_FROZEN = getattr(sys, "frozen", False)


def _user_data_root() -> Path:
    """桌面版用户数据根目录。

    定位策略 (按优先级):
      1. 环境变量 DATA_DIR (pydantic-settings 自动注入到 settings.data_dir, 不在此处理)
      2. 打包桌面版: exe 同级的 data/ 子目录 (<安装目录>/data/)
         —— 与程序同处一个总目录 (用户选择的安装目录), 视觉直观, 便于备份/迁移。
      3. 非 frozen (开发模式): 项目根 data/

    为什么不用 platformdirs 默认 (%LOCALAPPDATA%) 作为主路径:
      - 落在 C 盘系统目录, 用户不易察觉, 占系统盘空间
      - 用户期望「数据跟随程序」(便于备份/迁移)
    为什么放 {app}/data (exe 旁的 data/) 而非 {app} 外的兄弟目录:
      - 用户体验: 用户选了安装目录, 自然期望「程序和数据都在这」, 单一总目录更直观。
      - 数据安全: Inno Setup 覆盖安装(升级)时只往 {app} 写新程序文件, 不会清空
        目录里不在安装清单上的运行时文件 (data/ 即此类), 故覆盖安装不丢数据。
        (注意: 卸载时需在 .iss 中豁免 data/, 见 packaging/one-trading.iss 的 [UninstallDelete]。)
    旧版本数据迁移: 见 DataStore._migrate_legacy_data_dir(), 老用户首次启动自动搬迁。
    """
    # 打包桌面版: exe 同级的 data/ 子目录 (与程序同一总目录, 覆盖安装不丢数据)
    if _IS_FROZEN:
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir / "data"

    # 开发模式: 项目根 data/
    return _PROJECT_ROOT / "data"


def _resource_root() -> Path:
    """只读资源根目录。

    frozen: PyInstaller 解压目录 (_MEIPASS)
    非 frozen: 项目根目录 (源码树)
    """
    if _IS_FROZEN:
        # sys._MEIPASS 是 PyInstaller 注入的解压根
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent.parent


def _project_root() -> Path:
    """项目根目录 (非 frozen 用)。"""
    return Path(__file__).resolve().parent.parent.parent


_PROJECT_ROOT = _project_root()
_RESOURCE_ROOT = _resource_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_RESOURCE_ROOT / ".env") if not _IS_FROZEN else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TickFlow
    tickflow_api_key: str = Field(default="", description="留空启用 free 模式")

    # AI
    ai_provider: str = "openai_compat"
    ai_base_url: str = "https://api.deepseek.com"
    ai_api_key: str = ""
    ai_model: str = "deepseek-chat"
    ai_codex_command: str = "codex"
    # AI 访问模式:
    # - self_hosted: 兼容原有本地/桌面版, 由设置页管理 provider/key。
    # - cloud_subscription: APK 私人云实例, provider/key 只从服务端环境变量读取。
    ai_access_mode: str = "self_hosted"
    ai_subscription_enabled: bool = False
    ai_subscription_plan: str = "AI"
    # Extra hosted subscriptions for local/server-owned OpenAI-compatible relays.
    # Keys stay deployment-owned; the settings page never accepts them from APK.
    ai_86gamestore_api_key: str = ""
    ai_subrouter_api_key: str = ""
    # 默认浏览器风格 UA,绕过 Cloudflare 等 CDN/WAF 的 Bot 拦截(Issue #8)。
    # 用户可在 AI 设置页按需修改。
    ai_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 3018
    log_level: str = "INFO"
    backtest_range_guard: bool = False
    cookie_secure: bool = False
    release_channel: str = "development"
    build_sha: str = "local"

    # Auth / multi-tenancy. AUTH_PASSWORD remains the one-time owner bootstrap
    # credential for backward compatibility with the private release.
    auth_password: str = ""
    auth_owner_username: str = "admin"
    # Comma-separated direct peer IPs that may supply X-Forwarded-For.
    # Empty by default so a direct client cannot spoof its source address.
    auth_trusted_proxy_ips: str = ""
    # Public signup is available by default for the multi-user product. A
    # deployment can still set PUBLIC_REGISTRATION_ENABLED=false as an
    # emergency abuse-control switch without changing code or stored users.
    public_registration_enabled: bool = True
    public_registration_invite_code: str = ""
    public_registration_daily_per_ip: int = 3
    public_max_users: int = 100
    user_ai_daily_quota: int = 20
    user_watchlist_limit: int = 100
    user_session_ttl_days: int = 30

    # Hermes multi-user Agent. Disabled by default: enabling it requires a
    # Hermes gateway started with gateway.multiplex_profiles=true. The one
    # gateway then serves each account through /p/<profile>/ while Hermes
    # keeps config, credentials, sessions and memory in separate HERMES_HOME
    # directories.
    hermes_multiuser_enabled: bool = Field(
        default=False,
        validation_alias="ONE_TRADING_HERMES_MULTIUSER_ENABLED",
    )
    hermes_runtime_enabled: bool = Field(
        default=False,
        validation_alias="ONE_TRADING_HERMES_RUNTIME_ENABLED",
    )
    hermes_profiles_root: Path = Field(
        default_factory=lambda: Path.home() / ".hermes",
        validation_alias="ONE_TRADING_HERMES_ROOT",
    )
    hermes_gateway_base_url: str = Field(
        default="http://127.0.0.1:8650",
        validation_alias="ONE_TRADING_HERMES_BASE_URL",
    )
    hermes_owner_profile: str = Field(
        default="ot-owner",
        validation_alias="ONE_TRADING_HERMES_PROFILE",
    )
    hermes_python: Path = Field(
        default_factory=lambda: (
            Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"
        ),
        validation_alias="ONE_TRADING_HERMES_PYTHON",
    )
    hermes_runtime_bin: str = Field(
        default="",
        validation_alias="HERMES_RUNTIME_BIN",
    )
    hermes_runtime_cwd: str = Field(
        default="",
        validation_alias="HERMES_RUNTIME_CWD",
    )
    hermes_internal_base_url: str = Field(
        default="",
        validation_alias="ONE_TRADING_INTERNAL_BASE_URL",
    )

    # polars collect 并发闸 — kline_sync / repository 导入 polars_guard 时读取。
    # 908 字段本地未接齐会导致独立 venv 下分钟测试无法收集。
    polars_collect_permits: int = 4
    polars_collect_background_permits: int = 2

    # Data — frozen: exe 同级 data/ 子目录; 非 frozen: 项目根 data/
    # (均可被环境变量 DATA_DIR 覆盖, pydantic-settings 自动注入)
    data_dir: Path = _user_data_root()

    # Optional read-only QuantDB package root. Empty/unset keeps offline_quantdb off.
    # Source default must not hardcode a machine path; only an env/settings value enables it.
    offline_quantdb_root: Path | None = Field(default=None)

    # tiers.yaml 路径 — frozen: 资源目录内; 非 frozen: 项目根目录
    tiers_yaml: Path = _RESOURCE_ROOT / "tiers.yaml" if _IS_FROZEN else _PROJECT_ROOT / "tiers.yaml"

    # 静态文件(前端 dist) — frozen: 资源目录的 static/; 非 frozen: frontend/dist
    static_dir: Path = (
        _RESOURCE_ROOT / "static"
        if _IS_FROZEN
        else (_PROJECT_ROOT / "frontend" / "dist")
    )

    @field_validator("offline_quantdb_root", mode="before")
    @classmethod
    def _empty_offline_quantdb_root(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _resolve_paths(self) -> Settings:
        """确保 data_dir 是绝对路径（环境变量传入的相对路径基于项目根目录解析）。"""
        if not self.data_dir.is_absolute():
            # 相对路径基于项目根目录解析，而非 CWD
            self.data_dir = (_PROJECT_ROOT / self.data_dir).resolve()
        if self.offline_quantdb_root is not None:
            if not self.offline_quantdb_root.is_absolute():
                self.offline_quantdb_root = (
                    _PROJECT_ROOT / self.offline_quantdb_root
                ).resolve()
            else:
                self.offline_quantdb_root = self.offline_quantdb_root.resolve()
        if not self.hermes_profiles_root.is_absolute():
            self.hermes_profiles_root = (
                _PROJECT_ROOT / self.hermes_profiles_root
            ).resolve()
        if not self.hermes_python.is_absolute():
            self.hermes_python = (_PROJECT_ROOT / self.hermes_python).resolve()
        return self

    @property
    def use_free_mode(self) -> bool:
        """是否走 Free 模式。优先看 secrets.json,其次看 .env。"""
        from app import secrets_store
        return not secrets_store.get_tickflow_key()


settings = Settings()


def background_jobs_disabled() -> bool:
    """Fixture/isolated servers skip daily/extpull/financial/minute/quote/depth schedulers.

    Product default remains enabled. Only an explicit env opt-in disables background work.
    """
    return os.environ.get("ONE_TRADING_DISABLE_BACKGROUND", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
