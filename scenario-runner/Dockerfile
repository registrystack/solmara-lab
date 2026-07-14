FROM python:3.12-alpine

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV SCENARIO_RUNNER_HOST=0.0.0.0
ENV SCENARIO_RUNNER_PORT=8080

# Runtime dependencies (currently just cryptography, for holder proof signing)
# are declared in the repo-root uv.lock. Export and install the exact locked
# versions rather than letting pip resolve them independently.
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && rm -f requirements.txt

COPY scenarios ./scenarios
COPY scenario-runner ./scenario-runner
COPY scripts/relay_workload_identity_agent.py ./scripts/relay_workload_identity_agent.py

EXPOSE 8080
CMD ["python", "scenario-runner/server.py"]
