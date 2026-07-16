# Solmara Lab Performance Harness

This k6 harness exercises four live evaluation paths through the Solmara demo
stack: the Child Benefit Federator and the CRA, SIPF, and NAgDI authority-owned
Notaries. It assumes the lab has generated `.env` secrets and the local Docker
Compose topology is running.

## Start the Lab

```bash
just setup
just generate
just up
```

Wait for the standard smoke prerequisites to pass before collecting a baseline:

```bash
just smoke
```

## Run with Local k6

```bash
set -a
. .env
set +a
mkdir -p output/perf/results output/perf/reports

k6 run perf/k6/notary_relay_backed.js
```

The default profile is `smoke`. It intentionally uses a small VU count and a
short think time to validate routes without creating load. It is not a capacity
measurement.

The generated `.env` supplies the required bearer tokens:

- `CHILD_BENEFIT_FEDERATOR_TOKEN`
- `CRA_PENSION_CLIENT_TOKEN`
- `SIPF_PENSION_CLIENT_TOKEN`
- `NAGDI_NOTARY_TOKEN`

The scenario uses these target URLs and local defaults:

| Target | Environment variable | Default |
| --- | --- | --- |
| Child Benefit Federator | `CHILD_BENEFIT_FEDERATOR_URL` | `http://127.0.0.1:4321` |
| CRA Notary | `CRA_NOTARY_URL` | `http://127.0.0.1:4325` |
| SIPF Notary | `SIPF_NOTARY_URL` | `http://127.0.0.1:4322` |
| NAgDI Notary | `NAGDI_NOTARY_URL` | `http://127.0.0.1:4323` |

Run a capacity baseline with an explicit arrival rate:

```bash
REGISTRY_LAB_PROFILE=capacity \
REGISTRY_LAB_DURATION=2m \
REGISTRY_LAB_RATE=200 \
REGISTRY_LAB_PRE_ALLOCATED_VUS=64 \
REGISTRY_LAB_MAX_VUS=400 \
k6 run perf/k6/notary_relay_backed.js
```

Run a breakpoint ramp:

```bash
REGISTRY_LAB_PROFILE=breakpoint \
REGISTRY_LAB_STAGES=1m:100,1m:200,1m:400,30s:0 \
REGISTRY_LAB_PRE_ALLOCATED_VUS=64 \
REGISTRY_LAB_MAX_VUS=400 \
k6 run perf/k6/notary_relay_backed.js
```

## Run with Docker k6

Docker Desktop on macOS does not support `--network host` the same way Linux
does. Use `host.docker.internal` for loopback services:

```bash
docker run --rm \
  --env-file .env \
  -e CHILD_BENEFIT_FEDERATOR_URL=http://host.docker.internal:4321 \
  -e CRA_NOTARY_URL=http://host.docker.internal:4325 \
  -e SIPF_NOTARY_URL=http://host.docker.internal:4322 \
  -e NAGDI_NOTARY_URL=http://host.docker.internal:4323 \
  -v "$PWD:/workspace" \
  -w /workspace \
  grafana/k6:0.57.0 run perf/k6/notary_relay_backed.js
```

## Profiles

The scenario is profile-aware via `REGISTRY_LAB_PROFILE`:

- `smoke`: `constant-vus`, defaults to `REGISTRY_LAB_VUS=4`,
  `REGISTRY_LAB_DURATION=30s`, and `REGISTRY_LAB_THINK_TIME_SECONDS=0.1`.
  This catches broken routes, auth drift, and basic latency regressions.
- `capacity`: `constant-arrival-rate`, defaults to the script's baseline target
  rate and `REGISTRY_LAB_THINK_TIME_SECONDS=0`. Use this for comparable
  requests-per-second baselines.
- `breakpoint`: `ramping-arrival-rate`, defaults to the script's ramp stages
  and `REGISTRY_LAB_THINK_TIME_SECONDS=0`. Use this to find the first target
  rate where latency or error thresholds fail.

Common overrides:

- `REGISTRY_LAB_PROFILE=smoke|capacity|breakpoint`
- `REGISTRY_LAB_DURATION=30s`
- `REGISTRY_LAB_VUS=4`
- `REGISTRY_LAB_RATE=200`
- `REGISTRY_LAB_PRE_ALLOCATED_VUS=64`
- `REGISTRY_LAB_MAX_VUS=400`
- `REGISTRY_LAB_START_RATE=0`
- `REGISTRY_LAB_THINK_TIME_SECONDS=0`
- `REGISTRY_LAB_STAGES=1m:100,1m:200,1m:400,30s:0`

Keep hosted or shared environments opt-in; the default URLs are local loopback
ports.

`notary_relay_backed` defaults to `200 req/s` for capacity runs and ramps from
`100` to `200` to `400 req/s` for breakpoint runs.

## Reports

The script writes:

- `output/perf/results/<scenario>.json`
- `output/perf/reports/<scenario>.txt`

The text summaries print the active profile, think time, rate/count gauges,
latency distributions (`avg`, `med`, `p90`, `p95`, `p99`, `max`), and
status-code counters. Status-specific counters are emitted as first-class
metrics because k6 does not include tag cardinality in the compact text summary.
