"""首次部署引导 CLI：调用后端 /api/v1/setup/init-admin 创建第一个 admin。

支持两种模式：

1. 交互式（开发用）：
   python -m scripts.init_admin --base-url http://localhost:8000
   → 提示输入 username / email / password / password(确认)

2. 非交互（Docker / CI 自动化）：
   ADMIN_USERNAME=admin ADMIN_EMAIL=admin@x ADMIN_PASSWORD='xxx' \\
     python -m scripts.init_admin --base-url http://localhost:8000

退出码：
- 0  成功（新建 admin）或已初始化（幂等）
- 1  服务端拒绝（弱密码 / 已存在等）
- 2  网络错误（API 不可达）
- 3  参数错误
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


def _prompt(label: str, env: str | None, default: str = "", secret: bool = False) -> str:
    """从 env 读取，否则交互式提示。"""
    if env is not None and env != "":
        return env
    if secret:
        return getpass.getpass(f"{label}: ") or default
    return input(f"{label}{(': ' + default) if default else ''}: ").strip() or default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="首次部署引导：创建第一个 admin 用户")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="后端 API base URL")
    args = parser.parse_args(argv)

    url = f"{args.base_url.rstrip('/')}/api/v1/setup/init-admin"

    # 1) 先探查 status，决定走哪条路径
    try:
        status_resp = httpx.get(f"{args.base_url.rstrip('/')}/api/v1/setup/status", timeout=5)
        status_resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[ERR] 无法连接 {args.base_url}: {exc}", file=sys.stderr)
        return 2

    status_body = status_resp.json().get("data", {})
    if status_body.get("initialized"):
        print(
            "[OK] 系统已初始化（无需重复创建）。"
            "如需新建用户，请使用 /api/v1/auth/register 或 admin 控制台。"
        )
        return 0

    # 2) 收集凭据
    username = _prompt("Username", os.environ.get("ADMIN_USERNAME"), "admin")
    email = _prompt("Email", os.environ.get("ADMIN_EMAIL"), f"{username}@shm.local")
    password = _prompt("Password", os.environ.get("ADMIN_PASSWORD"), secret=True)
    if not os.environ.get("ADMIN_PASSWORD"):
        confirm = _prompt("Password (再次输入确认)", None, secret=True)
        if password != confirm:
            print("[ERR] 两次输入的密码不一致", file=sys.stderr)
            return 3

    # 3) 调 init-admin
    try:
        resp = httpx.post(
            url,
            json={"username": username, "email": email, "password": password},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        print(f"[ERR] 提交失败: {exc}", file=sys.stderr)
        return 2

    body = resp.json()
    if resp.status_code == 201 and body.get("code") == "OK":
        data = body["data"]
        print(
            f"[OK] admin 已创建（id={data['admin_id']}, username={data['username']}）\n"
            f"     access_token: {data['access_token'][:32]}...\n"
            f"     refresh_token: {data['refresh_token'][:32]}...\n"
            f"     强烈建议：立即修改 .env 中的 SECRET_KEY 与 EDGE_API_KEY"
        )
        return 0

    if resp.status_code == 409:
        print(f"[OK] 已是幂等成功：{body.get('message', '已初始化')}")
        return 0

    print(
        f"[ERR] 服务端拒绝 ({resp.status_code}): {body.get('message', resp.text)}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
