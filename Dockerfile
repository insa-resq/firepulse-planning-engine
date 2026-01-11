FROM python:3.12-slim AS build

WORKDIR /app

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml .

RUN pip install --no-cache-dir "."

FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=build /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY src/ ./src/

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "9000"]
