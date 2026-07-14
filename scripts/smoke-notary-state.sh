#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --env-file "$root/versions.env" --env-file "$root/.env" -f "$root/compose.yaml")

notaries=(
  "cra-notary:/etc/registry-notary/notary.yaml"
  "nia-notary:/etc/registry-notary/notary.yaml"
  "sro-notary:/etc/registry-notary/notary.yaml"
  "programme-notary:/etc/registry-notary/notary.yaml"
  "sipf-notary:/etc/registry-notary/notary.yaml"
  "nagdi-notary:/etc/registry-notary/notary.yaml"
)

mutable_tables=(
  replay_identifier
  consumable_nonce
  evaluation
  batch_idempotency
  credential_status
  machine_quota
  subject_access_quota
  preauthorization_login_state
  preauthorization_tx_code
)

doctor_all() {
  local target service config
  for target in "${notaries[@]}"; do
    service=${target%%:*}
    config=${target#*:}
    "${compose[@]}" --profile wallet run --rm --no-deps "$service" \
      --config "$config" state doctor >/dev/null
    printf 'notary-state: %s ready\n' "$service"
  done
}

state_snapshot() {
  local tables
  tables=$(printf '%s ' "${mutable_tables[@]}")
  # The single-quoted script expands only inside the PostgreSQL container.
  # shellcheck disable=SC2016
  "${compose[@]}" exec -T \
    -e "SOLMARA_NOTARY_STATE_TABLES=$tables" \
    postgres sh -eu -c '
      user=${POSTGRES_USER:-solmara_registry}
      for authority in cra nia sro programme sipf nagdi; do
        database="solmara_notary_${authority}"
        for table in $SOLMARA_NOTARY_STATE_TABLES; do
          count=$(psql -X -v ON_ERROR_STOP=1 -U "$user" -d "$database" -Atc \
            "SELECT count(*) FROM registry_notary_private.${table}")
          printf "%s|%s|%s\n" "$authority" "$table" "$count"
        done
      done
    ' | sort
}

wait_for_health() {
  local deadline service container status all_healthy
  deadline=$((SECONDS + 180))
  while (( SECONDS < deadline )); do
    all_healthy=1
    for target in "${notaries[@]}"; do
      service=${target%%:*}
      container=$("${compose[@]}" ps -q "$service")
      if [[ -z "$container" ]]; then
        all_healthy=0
        break
      fi
      status=$(docker inspect --format '{{.State.Health.Status}}' "$container")
      if [[ "$status" != healthy ]]; then
        all_healthy=0
        break
      fi
    done
    if (( all_healthy )); then
      return 0
    fi
    sleep 2
  done
  printf 'notary-state: authority Notaries did not recover readiness after restart\n' >&2
  return 1
}

doctor_all
before=$(state_snapshot)
mutable_count=$(printf '%s\n' "$before" | awk -F '|' '{ total += $3 } END { print total + 0 }')
if (( mutable_count == 0 )); then
  printf 'notary-state: no correctness rows exist; run the live smoke before the restart canary\n' >&2
  exit 1
fi

services=()
for target in "${notaries[@]}"; do
  services+=("${target%%:*}")
done
"${compose[@]}" restart "${services[@]}" >/dev/null
wait_for_health

doctor_all
after=$(state_snapshot)
if [[ "$before" != "$after" ]]; then
  printf 'notary-state: correctness row counts changed across restart\n' >&2
  diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") >&2 || true
  exit 1
fi
printf 'notary-state: restart preserved %s correctness rows across six authority databases\n' "$mutable_count"
