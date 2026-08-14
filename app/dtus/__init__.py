"""DTU 监听接入（v0.9）。

拓扑 A（DTU 直连云）的云端接入：独立 asyncio 进程接收 DTU 透传的
Modbus RTU 帧，解析后经 data_service.batch_ingest 直写时序库，
与 FastAPI 进程完全解耦。部署形态：同镜像独立进程（docker-compose 一个 service）。
"""
