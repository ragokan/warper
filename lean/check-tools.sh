#!/usr/bin/env bash
set -euo pipefail
for command in rg python3; do
    command -v "$command" >/dev/null || { echo "Required tool missing: $command" >&2; exit 1; }
done
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d /tmp/warp-lean-check.XXXXXX)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin"
cat > "$work/bin/cargo" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$LEAN_CHECK_ARGS"
MOCK
chmod +x "$work/bin/"*
export PATH="$work/bin:$PATH" LEAN_CHECK_ARGS="$work/args"
export CARGO_TARGET_DIR="$work/target"
[[ $("$repo/lean/build.sh") == "$work/target/lean/warp-oss" ]]
python3 - "$work/args" <<'PY'
import sys
from pathlib import Path
args = Path(sys.argv[1]).read_text().splitlines()
assert '--locked' in args and '--no-default-features' in args
features = set(args[args.index('--features') + 1].split(','))
assert {'lean', 'jemalloc', 'settings_file', 'ligatures', 'pluggable_notifications'} <= features
assert not features & {'gui', 'voice_input', 'release_bundle', 'agent_mode', 'factory_mcp', 'crash_reporting'}
assert not any(feature.startswith('nld_') for feature in features)
PY
git init -q -b master "$work/upstream"
git -C "$work/upstream" -c user.name=Check -c user.email=check@example.invalid commit -qm initial --allow-empty
git clone -q "$work/upstream" "$work/fork"
git -C "$work/fork" remote rename origin upstream
git -C "$work/fork" switch -qc lean
mkdir "$work/fork/lean"
cp "$repo/lean/sync.sh" "$work/fork/lean/"
git -C "$work/fork" add lean/sync.sh
git -C "$work/fork" -c user.name=Check -c user.email=check@example.invalid commit -qm lean
printf 'new upstream\n' > "$work/upstream/new-file"
git -C "$work/upstream" add new-file
git -C "$work/upstream" -c user.name=Check -c user.email=check@example.invalid commit -qm update
GIT_COMMITTER_NAME=Check GIT_COMMITTER_EMAIL=check@example.invalid "$work/fork/lean/sync.sh"
[[ $(git -C "$work/fork" branch --show-current) == lean ]]
[[ $(git -C "$work/fork" rev-parse master) == "$(git -C "$work/upstream" rev-parse master)" ]]
[[ $(git -C "$work/fork" config --local --get rerere.enabled) == true ]]
git -C "$work/fork" merge-base --is-ancestor master lean
printf 'dirty\n' > "$work/fork/dirty"
if "$work/fork/lean/sync.sh" 2>/dev/null; then
    echo 'sync accepted a dirty worktree' >&2
    exit 1
fi
rm "$work/fork/dirty"
printf 'lean change\n' > "$work/fork/new-file"
git -C "$work/fork" add new-file
git -C "$work/fork" -c user.name=Check -c user.email=check@example.invalid commit -qm conflict
printf 'upstream change\n' > "$work/upstream/new-file"
git -C "$work/upstream" add new-file
git -C "$work/upstream" -c user.name=Check -c user.email=check@example.invalid commit -qm conflict
if GIT_COMMITTER_NAME=Check GIT_COMMITTER_EMAIL=check@example.invalid \
    "$work/fork/lean/sync.sh" > "$work/conflict-log" 2>&1; then
    echo 'sync did not report the rebase conflict' >&2
    exit 1
fi
[[ -d $work/fork/.git/rebase-merge ]]
[[ $(git -C "$work/fork" diff --name-only --diff-filter=U) == new-file ]]
rg -q 'Rebase stopped' "$work/conflict-log"
echo 'Build interface and upstream sync checks passed.'
