"""DTU 监听接入进程入口：python -m app.dtu_server

独立 asyncio 进程（拓扑 A：DTU 直连云），与 FastAPI 解耦。
docker-compose 部署：同镜像，command: python -m app.dtu_server
"""

from app.dtus.server import main

if __name__ == "__main__":
    main()
