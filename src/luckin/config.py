"""配置管理:profile.json + 环境变量。

profile.json 存用户档案(家门店、日常口味),环境变量存密钥(token、高德 key)。
两者分离:档案可分享(脱敏后),密钥绝不落盘到 git。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# 默认配置路径:~/.luckin/profile.json(与瑞幸官方 CLI 的 ~/.luckin/.env 同目录)
DEFAULT_PROFILE_PATH = Path.home() / ".luckin" / "profile.json"

# MCP endpoint(生产环境,从 luckin.exe 二进制挖出,官方页面未公开)
DEFAULT_ENDPOINT = "https://gwmcp.lkcoffee.com/order/user/mcp"


@dataclass
class HomeStore:
    """家门店配置"""
    deptId: int = 0
    deptName: str = ""
    number: str = ""  # App 体系编号,如 No.xxxx(仅展示,不能当 deptId 用)
    address: str = ""
    longitude: float = 0.0
    latitude: float = 0.0
    work_time: str = ""


@dataclass
class DailyOrder:
    """日常口味配置"""
    product_id: int = 0
    product_name: str = ""
    spec: dict = field(default_factory=dict)  # {size, temp, bean, ...} 人类可读规格
    skuCode: str = ""  # 切换好规格的成品 skuCode,日常下单直接用


@dataclass
class Profile:
    """完整用户档案"""
    home_store: HomeStore = field(default_factory=HomeStore)
    daily_order: DailyOrder = field(default_factory=DailyOrder)
    endpoint: str = DEFAULT_ENDPOINT

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        hs = d.get("home_store") or {}
        do = d.get("daily_order") or {}
        return cls(
            home_store=HomeStore(**{k: hs.get(k, getattr(HomeStore(), k, None)) for k in hs if hasattr(HomeStore, k)}),
            daily_order=DailyOrder(
                product_id=do.get("product_id", 0),
                product_name=do.get("product_name", ""),
                spec=do.get("spec", {}),
                skuCode=do.get("skuCode", ""),
            ),
            endpoint=d.get("endpoint", DEFAULT_ENDPOINT),
        )

    def to_dict(self) -> dict:
        return {
            "home_store": asdict(self.home_store),
            "daily_order": asdict(self.daily_order),
            "endpoint": self.endpoint,
        }


def get_profile_path() -> Path:
    """获取 profile.json 路径(可被 LUCKIN_PROFILE 环境变量覆盖)"""
    env = os.environ.get("LUCKIN_PROFILE")
    return Path(env) if env else DEFAULT_PROFILE_PATH


def load_profile() -> Profile:
    """加载 profile.json,不存在返回空 Profile"""
    path = get_profile_path()
    if not path.exists():
        return Profile()
    try:
        return Profile.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"profile.json 解析失败({path}): {e}")


def save_profile(profile: Profile) -> Path:
    """保存 profile.json(自动建目录)"""
    path = get_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def get_token() -> str:
    """获取瑞幸 MCP token(三级优先级,对齐官方 my-coffee skill v0.8.2 的 token 生命周期约束)。

    优先级:
      1. 环境变量 LUCKIN_MCP_ORDER_TOKEN(最高,CI/服务场景)
      2. ~/.luckin/.env 文件的 LUCKIN_MCP_ORDER_TOKEN(官方 CLI `luckin login` 产物,本地复用)
      3. 报错并引导

    token 绑定用户瑞幸账号,能真实下单扣款。.env 文件建议 chmod 600(Linux/macOS)。
    profile.json 不存 token(档案可分享,密钥绝不落盘 git)。
    """
    # 1. 环境变量
    token = os.environ.get("LUCKIN_MCP_ORDER_TOKEN", "").strip()
    if token:
        return token

    # 2. ~/.luckin/.env(官方 luckin CLI 登录产物)
    env_file = Path.home() / ".luckin" / ".env"
    if env_file.exists():
        token = _read_dotenv_key(env_file, "LUCKIN_MCP_ORDER_TOKEN")
        if token:
            return token

    # 3. 报错引导
    raise EnvironmentError(
        "未找到 LUCKIN_MCP_ORDER_TOKEN(环境变量和 ~/.luckin/.env 都没有)。\n"
        "获取方式:运行瑞幸官方 `luckin login`(扫码授权后写入 ~/.luckin/.env),\n"
        "或设为用户环境变量:\n"
        "  Windows: [Environment]::SetEnvironmentVariable('LUCKIN_MCP_ORDER_TOKEN','<token>','User')\n"
        "  Linux/macOS: export LUCKIN_MCP_ORDER_TOKEN=<token>"
    )


def _read_dotenv_key(path: Path, key: str) -> str:
    """从 dotenv 文件读指定 key(简单 KEY=value 解析,不执行 shell 展开)。

    不用 python-dotenv 依赖,保持零额外依赖。支持:value 去引号、去首尾空白、跳过注释/空行。
    """
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                v = v.strip().strip("'").strip('"')
                return v
    except (OSError, UnicodeDecodeError):
        pass
    return ""


def get_amap_key() -> Optional[str]:
    """获取高德 API key(可选,locate 命令用)"""
    return os.environ.get("AMAP_API_KEY", "").strip() or None
