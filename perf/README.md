# Solmara Lab performance harness

This k6 harness exercises four live Registry Evidence requirements backed by
the CRA, SIPF, and NAgDI Relay Records APIs. It assumes the local Compose
topology is running and a short-lived Mint token is available as
`SOLMARA_EVIDENCE_ACCESS_TOKEN`.

## Start the lab

```bash
just setup
just up-generated
just smoke
```

## Run with local k6

Load the generated environment, obtain a current Evidence token through the
normal Mint client flow, and export it without writing it to a report:

```bash
set -a
. .env
set +a
export SOLMARA_EVIDENCE_ACCESS_TOKEN='<short-lived token>'
mkdir -p output/perf/results output/perf/reports

K6_INSECURE_SKIP_TLS_VERIFY=true \
  k6 run perf/k6/evidence_relay_backed.js
```

The TLS override is for the generated local CA on `https://localhost:4341`.
Do not use it against a hosted target.

The default `smoke` profile uses a small virtual-user count and short think
time to catch broken routes, authorization drift, invalid Evidence response
shapes, and basic latency regressions. It is not a capacity measurement.

Run a capacity baseline with an explicit arrival rate:

```bash
REGISTRY_LAB_PROFILE=capacity \
REGISTRY_LAB_DURATION=2m \
REGISTRY_LAB_RATE=200 \
REGISTRY_LAB_PRE_ALLOCATED_VUS=64 \
REGISTRY_LAB_MAX_VUS=400 \
K6_INSECURE_SKIP_TLS_VERIFY=true \
k6 run perf/k6/evidence_relay_backed.js
```

Run a breakpoint ramp:

```bash
REGISTRY_LAB_PROFILE=breakpoint \
REGISTRY_LAB_STAGES=1m:100,1m:200,1m:400,30s:0 \
REGISTRY_LAB_PRE_ALLOCATED_VUS=64 \
REGISTRY_LAB_MAX_VUS=400 \
K6_INSECURE_SKIP_TLS_VERIFY=true \
k6 run perf/k6/evidence_relay_backed.js
```

## Run with Docker k6

Docker Desktop on macOS uses `host.docker.internal` for host loopback. Pass the
short-lived token through the environment and keep the local TLS exception
explicit:

```bash
docker run --rm \
  --env-file .env \
  -e SOLMARA_EVIDENCE_URL=https://host.docker.internal:4341 \
  -e SOLMARA_EVIDENCE_ACCESS_TOKEN \
  -e K6_INSECURE_SKIP_TLS_VERIFY=true \
  -v "$PWD:/workspace" \
  -w /workspace \
  grafana/k6:0.57.0 run perf/k6/evidence_relay_backed.js
```

## Profiles

- `smoke`: constant virtual users, defaulting to 4 users for 30 seconds with a
  0.1-second think time.
- `capacity`: constant arrival rate, defaulting to 200 requests per second.
- `breakpoint`: ramping arrival rate, defaulting from 100 to 200 to 400
  requests per second and then to zero.

Common overrides are `REGISTRY_LAB_DURATION`, `REGISTRY_LAB_VUS`,
`REGISTRY_LAB_RATE`, `REGISTRY_LAB_PRE_ALLOCATED_VUS`,
`REGISTRY_LAB_MAX_VUS`, `REGISTRY_LAB_START_RATE`,
`REGISTRY_LAB_THINK_TIME_SECONDS`, and `REGISTRY_LAB_STAGES`.

Keep shared or hosted environments opt-in. A hosted run requires explicit
authorization from the environment owner, a valid TLS chain, and an explicit
`SOLMARA_EVIDENCE_URL`.

## Reports

The script writes:

- `output/perf/results/evidence_relay_backed.json`
- `output/perf/reports/evidence_relay_backed.txt`

The reports contain aggregate rate, latency, check, and HTTP status metrics.
They must not contain the access token, request subject, or signed response.
