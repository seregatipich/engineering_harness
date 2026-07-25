#!/usr/bin/env bash
# Transcribe the commands that actually gate a merge, for the work-next-issue skill.
#
# The gate is CI's command, not the repo's convenience script. A local `npm test`
# that passes while CI's `npm test -- --coverage --coverageThreshold` fails is the
# single most expensive failure mode this skill has: the subagent goes green, the
# merge lands, the integration branch goes red, and the run pays for a diagnosis it
# could have avoided by reading the workflow once. So this script reads it once and
# prints it verbatim — the Brief's *Finish checklist* transcribes from here rather
# than from whatever the README claims.
#
# The `env:` blocks are collected for the same reason: they are the authoritative
# dev-safe values for credentials, DSNs and feature flags. Copy CI's rather than
# inventing values that only differ subtly from what the tests expect.
#
# Usage: bash ci_recipe.sh [<repo-root>]
#   <repo-root>  defaults to the enclosing git worktree's root, else the cwd.
#
# What it collects:
#   1. Every job in .github/workflows/*.yml|yaml — each `run:` exactly as written
#      (block scalars kept byte-for-byte), plus the job's services, env and
#      strategy.matrix.
#   2. Repo-local gates: .claude/verify.sh, scripts/verify*.sh, Makefile targets
#      matching check|verify|ci|test, lefthook, .husky/, .pre-commit-config.yaml,
#      and git config core.hooksPath.
#
# Env precedence within a job, flattened into one map so it can be sourced as-is:
# workflow-level `env:` < job-level `env:` < step-level `env:` (later steps win).
#
# YAML is parsed with whatever is installed, best first, and the parser used is
# named in the output so the caller knows how far to trust it:
#   yq (either mikefarah or python-yq) > python3 + PyYAML > a line-oriented
#   bash/awk fallback. The fallback handles the shapes GitHub Actions workflows
#   actually use — nested `jobs:`, `steps:` lists, `run:` block scalars, `services:`
#   and `env:` maps — and nothing more: it does not resolve anchors, flow-style
#   mappings, or multi-document files, and it reports `matrix` as raw YAML text
#   rather than as a structure. Treat a fallback recipe as a strong hint that still
#   wants one glance at the workflow file.
#
# Absence is data: no .github/ means `jobs: []` and exit 0, not an error.
#
# Output: human-readable sections, then a machine block
#   --- RECIPE JSON ---
#   { "parser": "...",
#     "jobs": [ {workflow, name, runs:[...], services:[...], env:{...}, matrix} ],
#     "local_gates": [ {kind, path, command} ] }
set -euo pipefail

command -v jq >/dev/null 2>&1 || {
  echo "ci_recipe.sh: required CLI 'jq' not found on PATH" >&2; exit 127; }

case "${1-}" in
  -h|--help) sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'; exit 0 ;;
esac
if (( $# > 1 )); then
  echo "usage: ci_recipe.sh [<repo-root>]" >&2; exit 2
fi

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[[ -d "$ROOT" ]] || { echo "ci_recipe.sh: not a directory: $ROOT" >&2; exit 2; }
ROOT="$(cd "$ROOT" && pwd)"

# --- parser selection --------------------------------------------------------
PARSER=""
probe='a: {b: 1}'
if command -v yq >/dev/null 2>&1; then
  if printf '%s\n' "$probe" | yq -o=json -I=0 '.' >/dev/null 2>&1; then
    PARSER="yq (mikefarah)"
  elif printf '%s\n' "$probe" | yq -c '.' >/dev/null 2>&1; then
    PARSER="yq (python-yq)"
  fi
fi
if [[ -z "$PARSER" ]] && command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
  PARSER="python3 + PyYAML"
fi
[[ -n "$PARSER" ]] || PARSER="line-oriented fallback (bash/awk, best effort)"

yaml_to_json() { # $1 = file; JSON of the whole document on stdout
  case "$PARSER" in
    "yq (mikefarah)") yq -o=json -I=0 '.' "$1" ;;
    "yq (python-yq)") yq -c '.' "$1" ;;
    *) python3 -c 'import json,sys,yaml; json.dump(yaml.safe_load(open(sys.argv[1])) or {}, sys.stdout)' "$1" ;;
  esac
}

# Shapes one parsed workflow document into this script's job model. Env values are
# stringified because YAML types them (a port becomes an int) while a shell needs text.
JQ_SHAPE='
def strvals: with_entries(.value |= (if type == "string" then . else tojson end));
def asmap: if type == "object" then . else {} end;
. as $doc |
{ file: $file,
  jobs: [ ($doc.jobs | asmap) | to_entries[] | .key as $id | .value as $j |
    { workflow: $file,
      name: $id,
      runs: [ ($j.steps // [])[] | select(type == "object" and .run != null) | .run ],
      contexts: [ ($j.steps // [])[] | select(type == "object" and .run != null)
                  | {"working-directory": ."working-directory", shell: .shell} ],
      services: [ ($j.services | asmap) | to_entries[] |
        { name: .key,
          image: (if (.value | type) == "object" then .value.image else .value end),
          ports: (if (.value | type) == "object" then (.value.ports // []) else [] end),
          env: (if (.value | type) == "object" then (.value.env | asmap | strvals) else {} end),
          options: (if (.value | type) == "object" then .value.options else null end) } ],
      env: ( (($doc.env | asmap)
              + ($j.env | asmap)
              + ([ ($j.steps // [])[] | select(type == "object") | (.env | asmap) ] | add // {}))
             | strvals ),
      matrix: ($j.strategy.matrix? // null) } ] }'

# --- line-oriented fallback ---------------------------------------------------
# Emits this script's job model as JSON for one workflow file. Indentation-driven:
# it tracks the indent that opened each block and pops the block when a non-blank
# line comes back to or above that column. Block scalars are copied verbatim,
# comments included, because inside a `run:` a `#` line is script, not YAML.
FALLBACK_AWK='
function jstr(s,   i,c,n,out) {
  out = ""; n = length(s)
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\") out = out "\\\\"
    else if (c == "\"") out = out "\\\""
    else if (c == "\n") out = out "\\n"
    else if (c == "\t") out = out "\\t"
    else if (c == "\r") out = out "\\r"
    else if (c >= " ") out = out c
  }
  return "\"" out "\""
}
function indent_of(line,   m) {
  if (line ~ /^[[:space:]]*$/) return -1
  m = match(line, /[^ ]/)
  return m - 1
}
function unquote(v) {
  sub(/[[:space:]]+$/, "", v)
  if (v ~ /^".*"$/ || v ~ /^'"'"'.*'"'"'$/) v = substr(v, 2, length(v) - 2)
  return v
}
function flush_run(   t) {
  t = runbuf
  sub(/\n+$/, "", t)
  runs[curjob] = runs[curjob] (runs_n[curjob]++ ? "," : "") jstr(t)
  in_run = 0; runbuf = ""
}
function flush_matrix(   t) {
  t = matbuf
  sub(/\n+$/, "", t)
  matrix[curjob] = jstr(t)
  in_matrix = 0; matbuf = ""
}
function new_job(name) {
  curjob = ++njob
  jobname[curjob] = name
  runs[curjob] = ""; runs_n[curjob] = 0
  envs[curjob] = ""; envs_n[curjob] = 0
  svcs[curjob] = ""; svcs_n[curjob] = 0
  matrix[curjob] = "null"
  cursvc = ""
}
function add_env(job, k, v) {
  envs[job] = envs[job] (envs_n[job]++ ? "," : "") jstr(k) ":" jstr(v)
}
function close_service() {
  if (cursvc == "") return
  svcs[curjob] = svcs[curjob] (svcs_n[curjob]++ ? "," : "") \
    "{\"name\":" jstr(cursvc) ",\"image\":" (svcimg == "" ? "null" : jstr(svcimg)) \
    ",\"ports\":[],\"env\":{" svcenv "},\"options\":null}"
  cursvc = ""; svcimg = ""; svcenv = ""; svcenv_n = 0
}
BEGIN { njob = 0; in_jobs = 0; job_ind = -1; mode = ""; in_run = 0; in_matrix = 0; wfenv = ""; wfenv_n = 0 }
{ sub(/\r$/, "") }
in_run {
  ind = indent_of($0)
  if (ind < 0) { if (run_base >= 0) runbuf = runbuf "\n"; next }
  if (ind > run_owner_ind) {
    if (run_base < 0) run_base = ind
    runbuf = runbuf substr($0, run_base + 1) "\n"
    next
  }
  flush_run()
}
in_matrix {
  ind = indent_of($0)
  if (ind < 0) { matbuf = matbuf "\n"; next }
  if (ind > mat_ind) { matbuf = matbuf substr($0, mat_base + 1) "\n"; next }
  flush_matrix()
}
{
  ind = indent_of($0)
  if (ind < 0) next
  if ($0 ~ /^[[:space:]]*#/) next

  if (mode == "svcenv" && ind <= env_ind) mode = "services"
  if (mode == "services" && ind <= svc_ind) { close_service(); mode = "" }
  else if (mode == "env" && ind <= env_ind) mode = ""
  if (mode == "services" && ind <= svc_ind + 1) close_service()

  if (in_jobs && ind == 0) in_jobs = 0
  if (!in_jobs && ind == 0 && $0 ~ /^jobs:[[:space:]]*$/) { in_jobs = 1; job_ind = -1; curjob = 0; mode = ""; next }

  if (!in_jobs) {
    if (ind == 0 && $0 ~ /^env:[[:space:]]*$/) { mode = "wfenv"; env_ind = 0; next }
    if (mode == "wfenv") {
      if (ind <= 0) { mode = "" }
      else if (match($0, /^[ ]*[A-Za-z_][A-Za-z0-9_.-]*:/)) {
        k = $0; sub(/^[ ]*/, "", k); sub(/:.*$/, "", k)
        v = $0; sub(/^[ ]*[^:]*:[ ]*/, "", v)
        wfenv = wfenv (wfenv_n++ ? "," : "") jstr(k) ":" jstr(unquote(v))
        next
      }
    }
    next
  }

  if (job_ind < 0 && ind > 0) job_ind = ind
  if (ind == job_ind && $0 ~ /^[ ]*[A-Za-z0-9_.\-]+:[[:space:]]*(#.*)?$/) {
    n = $0; sub(/^[ ]*/, "", n); sub(/:.*$/, "", n)
    close_service(); mode = ""
    new_job(n)
    next
  }
  if (curjob == 0) next

  if ($0 ~ /^[ ]*services:[[:space:]]*$/) { close_service(); mode = "services"; svc_ind = ind; next }
  if ($0 ~ /^[ ]*matrix:[[:space:]]*$/) { in_matrix = 1; mat_ind = ind; mat_base = ind; matbuf = ""; next }
  if ($0 ~ /^[ ]*env:[[:space:]]*$/) {
    if (mode == "services" && cursvc != "") { mode = "svcenv"; env_ind = ind }
    else { mode = "env"; env_ind = ind }
    next
  }

  if (mode == "services" && ind == svc_ind + 2 && $0 ~ /^[ ]*[A-Za-z0-9_.\-]+:[[:space:]]*(#.*)?$/) {
    close_service()
    cursvc = $0; sub(/^[ ]*/, "", cursvc); sub(/:.*$/, "", cursvc)
    svcimg = ""; svcenv = ""; svcenv_n = 0
    next
  }
  if (cursvc != "" && match($0, /^[ ]*image:[ ]*/)) {
    v = $0; sub(/^[ ]*image:[ ]*/, "", v); svcimg = unquote(v); next
  }
  if ((mode == "env" || mode == "svcenv") && ind > env_ind && match($0, /^[ ]*[A-Za-z_][A-Za-z0-9_.-]*:/)) {
    k = $0; sub(/^[ ]*/, "", k); sub(/:.*$/, "", k)
    v = $0; sub(/^[ ]*[^:]*:[ ]*/, "", v); v = unquote(v)
    if (mode == "svcenv") svcenv = svcenv (svcenv_n++ ? "," : "") jstr(k) ":" jstr(v)
    else add_env(curjob, k, v)
    next
  }

  if (match($0, /^[ ]*(- +)?run:[ ]*/)) {
    v = $0; sub(/^[ ]*(- +)?run:[ ]*/, "", v)
    run_owner_ind = ind
    if ($0 ~ /^[ ]*- +run:/) run_owner_ind = ind + 2
    sub(/[[:space:]]+$/, "", v)
    if (v ~ /^[|>][+-]?[0-9]*([[:space:]]+#.*)?$/) { in_run = 1; run_base = -1; runbuf = "" }
    else runs[curjob] = runs[curjob] (runs_n[curjob]++ ? "," : "") jstr(unquote(v))
    next
  }
}
END {
  if (in_run) flush_run()
  if (in_matrix) flush_matrix()
  close_service()
  printf "{\"file\":%s,\"jobs\":[", jstr(FILE)
  for (i = 1; i <= njob; i++) {
    if (i > 1) printf ","
    e = envs[i]
    if (wfenv != "") e = (e == "" ? wfenv : wfenv "," e)
    printf "{\"workflow\":%s,\"name\":%s,\"runs\":[%s],\"contexts\":[],\"services\":[%s],\"env\":{%s},\"matrix\":%s}", \
      jstr(FILE), jstr(jobname[i]), runs[i], svcs[i], e, matrix[i]
  }
  printf "]}\n"
}'

# The fallback merges workflow env by textual concatenation, so a job that redefines
# a workflow key would emit it twice; jq keeps the last, which is the right winner.
fallback_to_json() { awk -v FILE="$1" "$FALLBACK_AWK" "$1" | jq -c '.jobs |= map(.env |= (to_entries | from_entries))'; }

# Accumulating through files rather than shell arrays keeps this working on the
# bash 3.2 that ships with macOS, where `${#arr[@]}` on an empty array trips `set -u`.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
: >"$WORK/workflows.ndjson"
: >"$WORK/gates.ndjson"

# --- collect workflows --------------------------------------------------------
wf_dir="$ROOT/.github/workflows"
if [[ -d "$wf_dir" ]]; then
  while IFS= read -r f; do
    rel="${f#"$ROOT"/}"
    if [[ "$PARSER" == "line-oriented"* ]]; then
      doc="$(fallback_to_json "$f" 2>/dev/null || true)"
    else
      doc="$(yaml_to_json "$f" 2>/dev/null | jq -c --arg file "$rel" "$JQ_SHAPE" 2>/dev/null || true)"
    fi
    if [[ -z "$doc" ]]; then
      doc="$(jq -n --arg file "$rel" '{file:$file, jobs:[], unparsed:true}')"
    else
      doc="$(jq -c --arg file "$rel" '.file = $file | .jobs |= map(.workflow = $file)' <<<"$doc")"
    fi
    printf '%s\n' "$doc" >>"$WORK/workflows.ndjson"
  done < <(find "$wf_dir" -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) | sort)
fi
WORKFLOWS_JSON="$(jq -s -c '.' "$WORK/workflows.ndjson")"

# --- repo-local gates ---------------------------------------------------------
add_gate() { jq -n -c --arg k "$1" --arg p "$2" --arg c "$3" \
  '{kind:$k, path:$p, command:(if $c == "" then null else $c end)}' >>"$WORK/gates.ndjson"; }

for s in "$ROOT/.claude/verify.sh" "$ROOT/scripts/verify.sh"; do
  [[ -f "$s" ]] && add_gate "verify-script" "${s#"$ROOT"/}" "bash ${s#"$ROOT"/}"
done
while IFS= read -r s; do
  [[ -z "$s" ]] && continue
  [[ "$s" == "$ROOT/scripts/verify.sh" ]] && continue
  add_gate "verify-script" "${s#"$ROOT"/}" "bash ${s#"$ROOT"/}"
done < <(find "$ROOT/scripts" -maxdepth 1 -type f -name 'verify*.sh' 2>/dev/null | sort)

for mk in Makefile makefile GNUmakefile; do
  [[ -f "$ROOT/$mk" ]] || continue
  while IFS= read -r target; do
    [[ -z "$target" ]] && continue
    add_gate "make-target" "$mk" "make $target"
  done < <(grep -oE '^[A-Za-z0-9_][A-Za-z0-9_./-]*:([^=]|$)' "$ROOT/$mk" 2>/dev/null \
    | sed 's/:.*$//' | grep -Ei 'check|verify|ci|test' | sort -u)
  break
done

for lh in lefthook.yml lefthook.yaml .lefthook.yml .lefthook.yaml; do
  [[ -f "$ROOT/$lh" ]] && add_gate "lefthook" "$lh" "lefthook run pre-commit"
done
if [[ -d "$ROOT/.husky" ]]; then
  while IFS= read -r h; do
    [[ -z "$h" ]] && continue
    add_gate "husky-hook" "${h#"$ROOT"/}" "sh ${h#"$ROOT"/}"
  done < <(find "$ROOT/.husky" -maxdepth 1 -type f ! -name '*.md' 2>/dev/null | sort)
fi
[[ -f "$ROOT/.pre-commit-config.yaml" ]] && add_gate "pre-commit" ".pre-commit-config.yaml" "pre-commit run --all-files"

hooks_path="$(git -C "$ROOT" config --get core.hooksPath 2>/dev/null || true)"
[[ -n "$hooks_path" ]] && add_gate "core.hooksPath" "$hooks_path" ""

GATES_JSON="$(jq -s -c '.' "$WORK/gates.ndjson")"

FULL="$(jq -n -c --arg parser "$PARSER" --arg root "$ROOT" \
  --argjson wf "$WORKFLOWS_JSON" --argjson gates "$GATES_JSON" \
  '{parser:$parser, root:$root, workflows:$wf, local_gates:$gates}')"

# --- human-readable sections --------------------------------------------------
jq -r '
def ctx(i): (.contexts[i] // {}) as $c
  | [ (if $c["working-directory"] then "working-directory: " + $c["working-directory"] else empty end),
      (if $c.shell then "shell: " + $c.shell else empty end) ]
  | if length == 0 then "" else " (" + join(", ") + ")" end;
[ "CI recipe for " + .root,
  "parser: " + .parser,
  "",
  "== GitHub Actions ==",
  ( if (.workflows | length) == 0
    then "  no workflow files under .github/workflows -> jobs: []"
    else ( .workflows[] |
      [ "", "--- " + .file + " ---",
        (if .unparsed then "  could not be parsed by " + $parser + "; read this file by hand" else empty end),
        (if (.jobs | length) == 0 and (.unparsed | not) then "  (no jobs)" else empty end),
        ( .jobs[] |
          [ "", "  job: " + .name,
            (if .matrix then "    strategy.matrix: " + (.matrix | tojson) else empty end),
            (if (.services | length) > 0 then "    services:" else empty end),
            ( .services[] |
              "      " + .name + "  image=" + (.image // "?")
              + (if (.ports | length) > 0 then "  ports=" + (.ports | map(tostring) | join(",")) else "" end)
              + (if (.env | length) > 0 then "  env=" + (.env | tojson) else "" end)
              + (if .options then "  options=" + .options else "" end) ),
            (if (.env | length) > 0 then "    env (workflow < job < step, flattened):" else empty end),
            ( .env | to_entries[] | "      " + .key + "=" + .value ),
            (if (.runs | length) == 0 then "    runs: none" else "    runs (verbatim, " + ((.runs | length) | tostring) + "):" end),
            ( . as $job | .runs | to_entries[] | .key as $k | .value as $body
              | ((.key + 1) | tostring) as $i
              | "--- run " + $i + ($job | ctx($k)) + " ---\n" + $body + "\n--- end run " + $i + " ---" )
          ] | join("\n") )
      ] | join("\n") )
    end ),
  "",
  "== Repo-local gates ==",
  ( if (.local_gates | length) == 0
    then "  none found"
    else ( .local_gates[] | "  " + .kind + "  " + .path + (if .command then "   -> " + .command else "" end) )
    end ),
  "",
  "--- RECIPE JSON ---"
] | flatten | join("\n")' --arg parser "$PARSER" <<<"$FULL"

jq '{parser, jobs: [.workflows[].jobs[] | del(.contexts)], local_gates}' <<<"$FULL"
