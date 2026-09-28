FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
COPY backend ./backend
RUN pip install -r requirements.lock && pip install --no-deps .
COPY sources.yaml ./
CMD ["python", "-m", "ask_the_ref.download", "--list"]
