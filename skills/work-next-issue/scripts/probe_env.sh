#!/usr/bin/env bash
# Read-only environment profile for the work-next-issue skill (SKILL.md Step 2).
#
# Emits ONE JSON document describing what this machine and this repo actually
# have, so a run stops improvising a fresh set of probes every time. It is
# strictly read-only: it installs nothing, starts nothing, writes nothing, and
# it never picks the verification command — that judgement stays with the
# caller, which is why no key here names a test runner or a build target.
#
# Absence is data, never failure: a tool that is not installed, a repo with no
# .github/, a directory that is not a git checkout all come back as empty or
# false. The script exits 0 in every one of those cases; it exits non-zero only
# when invoked wrongly or when jq is missing.
#
# Usage: bash probe_env.sh [<repo-root>]   (default: the current directory)
#
# Output: single JSON object, object keys and arrays sorted so two runs diff
# cleanly:
#   root        {passwordless_sudo}                     — one `sudo -n true` probe
#   containers  [{name,path,version,daemon_responds}]   — docker/podman/nerdctl;
#               an installed client whose daemon does not answer is not a
#               usable runtime, so presence and liveness are reported apart
#   ports       {source,note,listening:[{port,address,process}]}
#   toolchains  [{name,version,path,on_path}]           — interpreters,
#               compilers and package managers found on $PATH *and* in the usual
#               user-space install roots. A run was once nearly reported blocked
#               over a perfectly good toolchain that simply sat outside $PATH,
#               so "not on $PATH" is reported as a property, not as absence.
#   repo        {path,manifests,lockfiles,compose,env_examples,setup_scripts,
#                make_targets,ci,agent_contracts:[{path,bytes}]} — repo-relative
#               paths, scanned to a bounded depth so monorepos surface their
#               sub-project manifests too. `compose` also carries devcontainer
#               definitions: both declare how to bring the environment up.
#   vcs         {is_git_repo,worktrees:[{path,branch}]}  — the run needs to know
#               which worktree already holds the integration branch before it
#               tries to check it out; a detached worktree reports branch null.
set -euo pipefail

command -v jq >/dev/null 2>&1 || { echo "probe_env.sh: required CLI 'jq' not found on PATH" >&2; exit 127; }

USAGE="usage: probe_env.sh [<repo-root>]"
case "${1-}" in
  -h|--help) echo "$USAGE"; exit 0 ;;
esac
if (( $# > 1 )); then
  echo "probe_env.sh: too many arguments" >&2
  echo "$USAGE" >&2
  exit 2
fi

ROOT_ARG="${1:-.}"
if [[ ! -d "$ROOT_ARG" ]]; then
  echo "probe_env.sh: '$ROOT_ARG' is not a directory" >&2
  echo "$USAGE" >&2
  exit 2
fi
ROOT="$(cd "$ROOT_ARG" && pwd -P)"

# Every external probe is bounded: a wedged daemon or a JVM tool that decides to
# resolve dependencies must not hang the run.
if command -v timeout >/dev/null 2>&1; then
  BOUND=(timeout 8)
  BOUND_SLOW=(timeout 15)
else
  BOUND=()
  BOUND_SLOW=()
fi

to_json_array() { # stdin: one string per line -> sorted, deduped JSON array
  jq -R . | jq -s 'map(select(length > 0)) | unique'
}

# ---------------------------------------------------------------- root access

if "${BOUND[@]}" sudo -n true >/dev/null 2>&1; then
  PASSWORDLESS_SUDO=true
else
  PASSWORDLESS_SUDO=false
fi

# ------------------------------------------------- executable search location

declare -A DIR_SEEN=()
declare -A DIR_ON_PATH=()
declare -a SEARCH_DIRS=()

add_search_dir() { # <dir> <1 if the dir came from $PATH>
  local raw="$1" from_path="$2" real
  [[ -d "$raw" ]] || return 0
  real="$(cd "$raw" 2>/dev/null && pwd -P)" || return 0
  if [[ -z "${DIR_SEEN[$real]:-}" ]]; then
    DIR_SEEN[$real]=1
    SEARCH_DIRS+=("$real")
  fi
  [[ "$from_path" == "1" ]] && DIR_ON_PATH[$real]=1
  return 0
}

while IFS= read -r -d ':' path_dir || [[ -n "$path_dir" ]]; do
  [[ -n "$path_dir" ]] && add_search_dir "$path_dir" 1
done < <(printf '%s:' "${PATH:-}")

if [[ -n "${HOME:-}" ]]; then
  shopt -s nullglob
  for extra in \
    "$HOME/.local/bin" "$HOME/bin" "$HOME/.local/go/bin" "$HOME/go/bin" \
    "$HOME/.cargo/bin" "$HOME"/.local/*/bin; do
    add_search_dir "$extra" 0
  done
  shopt -u nullglob

  # Version managers keep their real binaries several levels down, under a
  # per-version bin/ or a shims/ directory; the root alone finds nothing.
  for manager_root in "$HOME/.nvm" "$HOME/.asdf" "$HOME/.pyenv"; do
    [[ -d "$manager_root" ]] || continue
    while IFS= read -r found; do
      add_search_dir "$found" 0
    done < <(find "$manager_root" -maxdepth 4 -type d \( -name bin -o -name shims \) 2>/dev/null || true)
  done
fi

locate_executable() { # <name> -> absolute path, or empty
  local name="$1" dir
  for dir in ${SEARCH_DIRS[@]+"${SEARCH_DIRS[@]}"}; do
    if [[ -f "$dir/$name" && -x "$dir/$name" ]]; then
      printf '%s\n' "$dir/$name"
      return 0
    fi
  done
  return 0
}

extract_version() { # stdin: raw tool output -> first version-looking token
  grep -oE '[0-9]+(\.[0-9]+){1,3}([-+_][0-9A-Za-z][0-9A-Za-z.-]*)?' 2>/dev/null | head -n 1 || true
}

probe_version() { # <exe> <flag...> -> version string, or empty
  local exe="$1"; shift
  local out
  out="$("${BOUND_SLOW[@]}" "$exe" "$@" </dev/null 2>&1 | head -n 5)" || true
  printf '%s' "$out" | extract_version
}

# ----------------------------------------------------------------- toolchains
#
# One table, one probe loop: adding a language means adding a line here, never a
# new branch of shell. Tools whose version flag is not `--version` carry theirs.
IFS= read -r -d '' TOOL_TABLE <<'TOOLS' || true
ant|-version
ansible|--version
asdf|--version
bazel|--version
bun|--version
bundle|--version
cabal|--version
cargo|--version
cc|--version
clang|--version
clang++|--version
cmake|--version
composer|--version
conda|--version
corepack|--version
curl|--version
dart|--version
deno|--version
docker-compose|--version
dotnet|--version
elixir|--version
fnm|--version
g++|--version
gcc|--version
gem|--version
gh|--version
ghc|--version
git|--version
go|version
goenv|--version
gradle|--version
hatch|--version
helm|version --short
java|-version
javac|-version
jenv|--version
jq|--version
julia|--version
just|--version
kotlin|-version
kubectl|version --client
lua|-v
make|--version
mamba|--version
meson|--version
mise|--version
mix|--version
mongosh|--version
mvn|--version
mypy|--version
mysql|--version
nim|--version
ninja|--version
node|--version
nodenv|--version
nox|--version
npm|--version
npx|--version
pdm|--version
perl|--version
php|--version
pip|--version
pip3|--version
pipx|--version
pkg-config|--version
pnpm|--version
poetry|--version
psql|--version
pyenv|--version
pypy3|--version
python|--version
python3|--version
R|--version
rake|--version
rbenv|--version
rebar3|version
redis-cli|--version
ruby|--version
rustc|--version
rustup|--version
sbt|--version
scala|-version
shellcheck|--version
shfmt|--version
sqlite3|--version
stack|--version
swift|--version
task|--version
terraform|version
tox|--version
tsc|--version
uv|--version
volta|--version
wget|--version
yarn|--version
zig|version
TOOLS

declare -A TOOL_SEEN=()
TOOLCHAINS=()

while IFS='|' read -r tool_name version_flags; do
  [[ -n "$tool_name" && -n "$version_flags" ]] || continue
  read -r -a flags <<<"$version_flags"
  for dir in ${SEARCH_DIRS[@]+"${SEARCH_DIRS[@]}"}; do
    exe="$dir/$tool_name"
    [[ -f "$exe" && -x "$exe" ]] || continue
    # Shims and symlinks across several search dirs routinely land on one real
    # binary; report each distinct binary once.
    real="$(readlink -f "$exe" 2>/dev/null || printf '%s' "$exe")"
    key="$tool_name:$real"
    [[ -n "${TOOL_SEEN[$key]:-}" ]] && continue
    TOOL_SEEN[$key]=1
    version="$(probe_version "$exe" "${flags[@]}")"
    on_path=false
    [[ -n "${DIR_ON_PATH[$dir]:-}" ]] && on_path=true
    TOOLCHAINS+=("$(jq -nc --arg n "$tool_name" --arg v "$version" --arg p "$exe" --argjson op "$on_path" \
      '{name:$n, version:(if $v == "" then null else $v end), path:$p, on_path:$op}')")
  done
done <<<"$TOOL_TABLE"

if (( ${#TOOLCHAINS[@]} == 0 )); then
  toolchains_json='[]'
else
  toolchains_json="$(printf '%s\n' "${TOOLCHAINS[@]}" | jq -s 'sort_by(.name, .path)')"
fi

# ----------------------------------------------------------------- containers
#
# Presence and liveness are separate facts: a client binary with no reachable
# daemon cannot bring a service up, and reporting it as "docker available" is
# exactly how a run ends up blocked at verification time instead of here.
CONTAINERS=()
for runtime in docker nerdctl podman; do
  runtime_path="$(locate_executable "$runtime")"
  [[ -n "$runtime_path" ]] || continue
  runtime_version="$(probe_version "$runtime_path" --version)"
  if "${BOUND_SLOW[@]}" "$runtime_path" info >/dev/null 2>&1; then
    daemon_responds=true
  else
    daemon_responds=false
  fi
  CONTAINERS+=("$(jq -nc --arg n "$runtime" --arg p "$runtime_path" --arg v "$runtime_version" \
    --argjson d "$daemon_responds" \
    '{name:$n, path:$p, version:(if $v == "" then null else $v end), daemon_responds:$d}')")
done

if (( ${#CONTAINERS[@]} == 0 )); then
  containers_json='[]'
else
  containers_json="$(printf '%s\n' "${CONTAINERS[@]}" | jq -s 'sort_by(.name)')"
fi

# ---------------------------------------------------------------------- ports
#
# Each parser emits "port<TAB>address<TAB>process"; the process column is empty
# when the kernel will not disclose the owner (another user's socket, no root).
ports_source=null
ports_note=null
ports_rows=""

if command -v ss >/dev/null 2>&1; then
  ports_source='"ss"'
  ports_rows="$(ss -H -lntp 2>/dev/null | awk '
    {
      addr = $4
      n = split(addr, parts, ":")
      port = parts[n]
      host = substr(addr, 1, length(addr) - length(port) - 1)
      proc = ""
      if (match($0, /users:\(\("[^"]+"/)) proc = substr($0, RSTART + 9, RLENGTH - 10)
      print port "\t" host "\t" proc
    }' || true)"
elif command -v netstat >/dev/null 2>&1; then
  ports_source='"netstat"'
  ports_rows="$(netstat -lntp 2>/dev/null | awk '
    $1 ~ /^tcp/ {
      addr = $4
      n = split(addr, parts, ":")
      port = parts[n]
      host = substr(addr, 1, length(addr) - length(port) - 1)
      proc = ""
      if ($NF ~ /\//) { split($NF, owner, "/"); proc = owner[2] }
      print port "\t" host "\t" proc
    }' || true)"
elif command -v lsof >/dev/null 2>&1; then
  ports_source='"lsof"'
  ports_rows="$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk '
    NR > 1 {
      addr = $9
      n = split(addr, parts, ":")
      port = parts[n]
      host = substr(addr, 1, length(addr) - length(port) - 1)
      print port "\t" host "\t" $1
    }' || true)"
else
  ports_note='"no ss, netstat or lsof on PATH; listening ports could not be enumerated"'
fi

listening_json="$(printf '%s\n' "$ports_rows" | jq -R . | jq -s '
  map(select(length > 0) | split("\t"))
  | map({port:(.[0] | tonumber? // null), address:(.[1] // ""), process:(if (.[2] // "") == "" then null else .[2] end)})
  | map(select(.port != null))
  | unique
  | sort_by(.port, .address, (.process // ""))')"

ports_json="$(jq -n --argjson s "$ports_source" --argjson n "$ports_note" --argjson l "$listening_json" \
  '{source:$s, note:$n, listening:$l}')"

# ----------------------------------------------------------------------- repo
#
# One bounded walk, then pure pattern matching over the result: cheaper than a
# find per category, and it keeps vendored trees out of every category at once.
REPO_FILES="$(cd "$ROOT" && find . -maxdepth 4 \
  \( -name .git -o -name node_modules -o -name vendor -o -name target \
     -o -name dist -o -name build -o -name .venv -o -name venv \
     -o -name __pycache__ -o -name .tox -o -name .mypy_cache -o -name .next \
     -o -name .gradle -o -name .terraform \) -prune -o -type f -print 2>/dev/null \
  | sed 's|^\./||' | sort || true)"

match_repo_files() { # <extended regex over the repo-relative path>
  printf '%s\n' "$REPO_FILES" | grep -E "$1" || true
}

MANIFEST_RE='(^|/)(package\.json|deno\.json|deno\.jsonc|pyproject\.toml|setup\.py|setup\.cfg|requirements[^/]*\.txt|Pipfile|environment\.yml|go\.mod|Cargo\.toml|pom\.xml|build\.gradle|build\.gradle\.kts|settings\.gradle|settings\.gradle\.kts|build\.sbt|Gemfile|composer\.json|[^/]+\.csproj|[^/]+\.fsproj|[^/]+\.sln|Package\.swift|mix\.exs|rebar\.config|stack\.yaml|[^/]+\.cabal|CMakeLists\.txt|meson\.build|BUILD\.bazel|WORKSPACE|Makefile|makefile|GNUmakefile|Taskfile\.ya?ml|justfile|Justfile|build\.zig|pubspec\.yaml|elm\.json)$'
LOCKFILE_RE='(^|/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|deno\.lock|poetry\.lock|uv\.lock|pdm\.lock|Pipfile\.lock|conda-lock\.yml|go\.sum|Cargo\.lock|Gemfile\.lock|composer\.lock|gradle\.lockfile|packages\.lock\.json|mix\.lock|cabal\.project\.freeze)$'
COMPOSE_RE='(^|/)(docker-compose[^/]*\.ya?ml|compose[^/]*\.ya?ml|Dockerfile[^/]*|devcontainer\.json)$'
ENV_EXAMPLE_RE='(^|/)\.env[^/]*(example|sample|template|dist|defaults)[^/]*$|(^|/)(example|sample|template)\.env$'
SETUP_SCRIPT_RE='(^|/)scripts/[^/]+$'
CI_RE='^\.github/workflows/[^/]+\.ya?ml$|(^|/)(\.gitlab-ci\.yml|azure-pipelines\.ya?ml|Jenkinsfile|\.travis\.yml)$|^\.circleci/[^/]+\.ya?ml$'
AGENT_CONTRACT_RE='(^|/)(AGENTS\.md|CLAUDE\.md|CONTRIBUTING\.md|\.cursorrules)$'

manifests_json="$(match_repo_files "$MANIFEST_RE" | to_json_array)"
lockfiles_json="$(match_repo_files "$LOCKFILE_RE" | to_json_array)"
compose_json="$(match_repo_files "$COMPOSE_RE" | to_json_array)"
env_examples_json="$(match_repo_files "$ENV_EXAMPLE_RE" | to_json_array)"
setup_scripts_json="$(match_repo_files "$SETUP_SCRIPT_RE" | to_json_array)"
ci_json="$(match_repo_files "$CI_RE" | to_json_array)"

make_targets=""
while IFS= read -r makefile; do
  [[ -n "$makefile" ]] || continue
  make_targets+="$(awk '
    /^[A-Za-z0-9][A-Za-z0-9._\/-]*([ \t]+[A-Za-z0-9._\/-]+)*[ \t]*:([^=]|$)/ {
      line = $0
      sub(/:.*/, "", line)
      n = split(line, names, /[ \t]+/)
      for (i = 1; i <= n; i++) if (names[i] != "") print names[i]
    }' "$ROOT/$makefile" 2>/dev/null || true)"$'\n'
done < <(match_repo_files '(^|/)(Makefile|makefile|GNUmakefile)$')
make_targets_json="$(printf '%s\n' "$make_targets" | to_json_array)"

AGENT_CONTRACTS=()
while IFS= read -r contract; do
  [[ -n "$contract" ]] || continue
  bytes="$(wc -c <"$ROOT/$contract" 2>/dev/null | tr -d ' ')"
  [[ -n "$bytes" ]] || bytes=0
  AGENT_CONTRACTS+=("$(jq -nc --arg p "$contract" --argjson b "$bytes" '{path:$p, bytes:$b}')")
done < <(match_repo_files "$AGENT_CONTRACT_RE")

if (( ${#AGENT_CONTRACTS[@]} == 0 )); then
  agent_contracts_json='[]'
else
  agent_contracts_json="$(printf '%s\n' "${AGENT_CONTRACTS[@]}" | jq -s 'sort_by(.path)')"
fi

repo_json="$(jq -n --arg path "$ROOT" \
  --argjson manifests "$manifests_json" \
  --argjson lockfiles "$lockfiles_json" \
  --argjson compose "$compose_json" \
  --argjson env_examples "$env_examples_json" \
  --argjson setup_scripts "$setup_scripts_json" \
  --argjson make_targets "$make_targets_json" \
  --argjson ci "$ci_json" \
  --argjson agent_contracts "$agent_contracts_json" \
  '{path:$path, manifests:$manifests, lockfiles:$lockfiles, compose:$compose,
    env_examples:$env_examples, setup_scripts:$setup_scripts,
    make_targets:$make_targets, ci:$ci, agent_contracts:$agent_contracts}')"

# ------------------------------------------------------------------------ vcs

is_git_repo=false
worktrees_json='[]'
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  is_git_repo=true
  worktrees_json="$(git -C "$ROOT" worktree list --porcelain 2>/dev/null | jq -R . | jq -s '
    map(select(length > 0))
    | [ foreach .[] as $line ({cur:{}, out:null};
          if   ($line | startswith("worktree "))
          then {cur:{path:($line[9:]), branch:null}, out:null}
          elif ($line | startswith("branch "))
          then {cur:(.cur + {branch:($line[7:] | sub("^refs/heads/"; ""))}), out:null}
          elif ($line | startswith("detached"))
          then {cur:(.cur + {branch:null}), out:null}
          else .
          end;
          .cur)
      ]
    | map(select(.path != null))
    | group_by(.path)
    | map(max_by(.branch != null))
    | sort_by(.path)' || true)"
  [[ -n "$worktrees_json" ]] || worktrees_json='[]'
fi

vcs_json="$(jq -n --argjson r "$is_git_repo" --argjson w "$worktrees_json" \
  '{is_git_repo:$r, worktrees:$w}')"

# --------------------------------------------------------------------- output

jq -n -S \
  --argjson root "$(jq -n --argjson s "$PASSWORDLESS_SUDO" '{passwordless_sudo:$s}')" \
  --argjson containers "$containers_json" \
  --argjson ports "$ports_json" \
  --argjson toolchains "$toolchains_json" \
  --argjson repo "$repo_json" \
  --argjson vcs "$vcs_json" \
  '{root:$root, containers:$containers, ports:$ports, toolchains:$toolchains,
    repo:$repo, vcs:$vcs}'
