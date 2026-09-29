FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 ASK_THE_REF_ROOT=/app
WORKDIR /app
COPY requirements.lock pyproject.toml ./
COPY backend ./backend
RUN pip install -r requirements.lock && pip install --no-deps .
COPY sources.yaml models.lock.json ./
COPY db ./db
CMD ["python", "-m", "ask_the_ref.download", "--list"]
