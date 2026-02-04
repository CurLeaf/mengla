FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 将 backend 作为包挂在 /app/backend 下
COPY . /app/backend

WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

