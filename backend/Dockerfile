FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# 昨日战报图片（/api/daily-review/image）需要中文字体
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --no-create-home logbook
COPY alembic.ini ./
COPY migrations/ migrations/
COPY logbook/ logbook/
USER 10001
# 只在内部网络里被 Caddy 访问（不对宿主机发布端口），所以信任任意上游的 X-Forwarded-For；
# Caddy 默认会覆盖客户端自带的该头，登录限速据此拿到真实来源 IP。
CMD ["uvicorn", "logbook.api:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
