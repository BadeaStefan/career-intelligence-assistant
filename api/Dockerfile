FROM python:3.12-slim

# uv resolves and installs from the committed lockfile, so the image gets the
# same dependency versions as the local venv rather than "whatever resolved
# today". That equivalence is the reproducibility claim in the README.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies are installed before the source is copied so that editing code
# does not invalidate the dependency layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

# Migrations run at start rather than in the image: the database is not
# reachable at build time, and the schema belongs to the deployment, not the
# artefact.
CMD ["sh", "-c", "alembic upgrade head && uvicorn career_intel.api.app:create_app --factory --host 0.0.0.0 --port 8000"]
