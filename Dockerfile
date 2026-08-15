# 信创开源生态数据分析系统 — Web 应用镜像
# 构建：docker build -t xinchuang-web .
# 运行：docker compose up -d（推荐，见 docker-compose.yml）

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 先装依赖（利用 Docker 层缓存，代码变动不用重装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝运行所需文件（只拷 Web 相关，ETL/数据/文档不进入镜像）
COPY backend/ backend/
COPY frontend/ frontend/
COPY project_config.py .

# 暴露大屏端口
EXPOSE 5000

# 启动：Flask 同时托管 API + 前端页面
CMD ["python", "backend/app.py"]
