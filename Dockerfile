FROM python:3.12-slim

WORKDIR /app

# 使用项目自带 venv（与 docker/entrypoint.sh 的 .venv/bin/ 路径一致），国内 pip 源
COPY requirements.txt .
RUN python -m venv .venv && \
    .venv/bin/pip install --no-cache-dir -r requirements.txt -i https://mirrors.ustc.edu.cn/pypi/simple

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
