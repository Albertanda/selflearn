#!/usr/bin/env bash
# Fixed-home launcher for this checkout.
#
# Resolve the repository from this script's real path (following symlinks), then
# run the checkout's own CLI with that directory as the runtime home. Callers may
# not override --home: the explicit Typer option would otherwise take precedence
# and silently create a second data tree somewhere else.
set -eu

die() {
    printf '%s\n' "$*" >&2
    exit 1
}

# Resolve symlinks to the real script first, then the directory, so invoking the
# wrapper through a symlink still finds the checkout that contains it.
source_path=${BASH_SOURCE[0]}
# CDPATH must not redirect relative paths or print extra lines into the command
# substitutions used to locate this checkout.
while [ -L "$source_path" ]; do
    source_dir=$(CDPATH= cd -P -- "$(dirname -- "$source_path")" && pwd)
    link_target=$(readlink -- "$source_path")
    case $link_target in
        /*) source_path=$link_target ;;
        *) source_path=$source_dir/$link_target ;;
    esac
done
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$source_path")" && pwd)
repo_root=$(CDPATH= cd -P -- "$script_dir/.." && pwd)

for arg in "$@"; do
    case $arg in
        --home|--home=*)
            die "start_selflearn.sh: refusing caller-supplied --home; this checkout always runs with DEEPTUTOR_HOME=$repo_root"
            ;;
    esac
done

venv_dir=$repo_root/.venv
cli=$venv_dir/bin/deeptutor
[ -d "$venv_dir" ] || die "start_selflearn.sh: missing virtualenv at $venv_dir (create it with python3.12 -m venv .venv and install .[dev]); refusing to fall back to PATH"
[ -x "$venv_dir/bin/python" ] || die "start_selflearn.sh: missing executable $venv_dir/bin/python; refusing to fall back to PATH"
[ -e "$cli" ] || die "start_selflearn.sh: missing local CLI at $cli (install the checkout into its .venv); refusing to fall back to PATH"
[ -x "$cli" ] || die "start_selflearn.sh: local CLI is not executable: $cli"

export DEEPTUTOR_HOME=$repo_root
cd -- "$repo_root"
exec "$cli" start --home "$repo_root" "$@"
