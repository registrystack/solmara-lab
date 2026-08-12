FROM python@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV SCENARIO_RUNNER_HOST=0.0.0.0
ENV SCENARIO_RUNNER_PORT=8080

# Runtime dependencies (currently just cryptography, for holder proof signing)
# are declared in the repo-root uv.lock. Export and install the exact locked
# versions rather than letting pip resolve them independently.
COPY --from=ghcr.io/astral-sh/uv@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && rm -f requirements.txt

COPY scenarios ./scenarios
COPY scenario-runner ./scenario-runner

EXPOSE 8080
CMD ["python", "scenario-runner/server.py"]
