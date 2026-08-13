"""HTTP JSON 协议适配器：轮询返回 JSON 数组的智能传感器 HTTP 接口。

期望对端返回格式：
[{"device_code": "...", "point_code": "...", "value": 1.23, "unit": "m/s2", "quality": "good"}, ...]
"""

import httpx

from app.plugins.protocols.base import ProtocolAdapter, ProtocolConfig, RawReading


class HttpJsonAdapter(ProtocolAdapter):
    name = "http_json"
    supports_batch = True

    def __init__(self, config: ProtocolConfig):
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        url = self.config.host
        if self.config.port:
            url = f"{url}:{self.config.port}"
        self._client = httpx.AsyncClient(
            base_url=url,
            timeout=self.config.timeout_ms / 1000,
            headers=self.config.auth.get("headers", {}),
        )
        self._connected = True

    async def read_batch(self) -> list[RawReading]:
        if not self._client:
            raise ConnectionError("HTTP client not connected")
        path = self.config.extra.get("path", "/readings")
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._last_error = str(exc)
            raise ConnectionError(f"HTTP 读取失败: {exc}") from exc

        ts = self._now()
        readings = []
        for item in resp.json():
            readings.append(
                RawReading(
                    device_code=item["device_code"],
                    point_code=item["point_code"],
                    timestamp=ts,
                    value=float(item["value"]),
                    unit=item.get("unit", ""),
                    quality=item.get("quality", "good"),
                    extra=item.get("extra", {}),
                )
            )
        return readings

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._connected = False
