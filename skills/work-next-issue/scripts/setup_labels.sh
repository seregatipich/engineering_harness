#!/usr/bin/env bash
# Create the labels the work-next-issue skill needs, and only those it is missing.
#
# Usage: bash setup_labels.sh <owner/repo> [--map <path>]
#   --map <path>   the label_map from select_batch.sh; `-` or omitted reads stdin.
#                  Accepts either select_batch.sh's whole JSON object or a bare
#                  {role: label|null} map.
#
#   bash select_batch.sh acme/app --priority high | tee /tmp/batch.json \
#     | bash setup_labels.sh acme/app
#
# A role mapped to a label already exists under that name — nothing is created,
# because a repo that says `priority:p0` and `status:in-progress` should not also
# acquire a second, parallel vocabulary it never asked for. A role mapped to null
# was probed and genuinely has no label: that one is created under its canonical
# name. A role absent from the map was not probed and is left alone.
#
# Output: the effective map on stdout — the input with every created role filled
# in, so the caller can use it directly. Progress goes to stderr. Exit 1 if a
# creation was attempted and failed (the role stays null in the output map).
set -euo pipefail

for c in gh jq; do
  command -v "$c" >/dev/null 2>&1 || { echo "setup_labels.sh: required CLI '$c' not found on PATH" >&2; exit 127; }
done

usage() { echo "usage: setup_labels.sh <owner/repo> [--map <path>]  (label_map JSON on stdin when --map is omitted)" >&2; }

REPO="${1-}"
[[ -n "$REPO" ]] || { usage; exit 2; }
shift

MAP_SRC=""
while (( $# )); do
  case "$1" in
    --map|-m) MAP_SRC="${2-}"; shift 2 || true ;;
    *) echo "setup_labels.sh: unknown argument '$1'" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$MAP_SRC" || "$MAP_SRC" == "-" ]]; then
  if [[ -t 0 ]]; then
    echo "setup_labels.sh: no label_map given. Pipe select_batch.sh's output in, or pass --map <path>." >&2
    usage; exit 2
  fi
  raw="$(cat)"
else
  [[ -r "$MAP_SRC" ]] || { echo "setup_labels.sh: cannot read map file '$MAP_SRC'" >&2; exit 2; }
  raw="$(cat -- "$MAP_SRC")"
fi

if ! map_json="$(jq -ce 'if type == "object" then (.label_map // .) else error("not an object") end' <<<"$raw" 2>/dev/null)" \
   || [[ "$(jq -r 'type' <<<"$map_json")" != "object" ]]; then
  echo "setup_labels.sh: input is not a label_map — expected a JSON object of role -> label|null (select_batch.sh's .label_map)" >&2
  exit 2
fi

role_color() { # canonical role -> the color used when this repo has no label for it
  case "$1" in
    priority:critical) printf 'b60205' ;;
    priority:high)     printf 'd93f0b' ;;
    priority:medium)   printf 'fbca04' ;;
    priority:low)      printf '0e8a16' ;;
    in-progress)       printf '1d76db' ;;
    awaiting-release)  printf '5319e7' ;;
  esac
}

FAILED=0
created=()
while IFS= read -r role; do
  [[ -z "$role" ]] && continue
  color="$(role_color "$role")"
  if [[ -z "$color" ]]; then
    echo "setup_labels.sh: '$role' is not a role this skill owns; not creating it" >&2
    continue
  fi
  if err="$(gh label create "$role" -c "$color" -R "$REPO" 2>&1)"; then
    created+=("$role")
    echo "created  $role on $REPO" >&2
  elif grep -qi 'already exists' <<<"$err"; then
    created+=("$role")
    echo "exists   $role on $REPO (created concurrently)" >&2
  else
    FAILED=1
    echo "FAILED   $role on $REPO: $err" >&2
  fi
done < <(jq -r 'to_entries[] | select(.value == null) | .key' <<<"$map_json")

while IFS= read -r line; do
  [[ -n "$line" ]] && echo "kept     $line" >&2
done < <(jq -r 'to_entries[] | select(.value != null) | "\(.key) -> this repo'"'"'s \(.value)"' <<<"$map_json")

created_json="$(printf '%s\n' ${created[@]+"${created[@]}"} | jq -R . | jq -sc 'map(select(length > 0))')"
jq --argjson made "$created_json" 'reduce $made[] as $r (.; .[$r] = $r)' <<<"$map_json"

exit "$FAILED"
