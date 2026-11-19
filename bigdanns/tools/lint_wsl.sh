#!/bin/bash
# lint_wsl.sh <repo>: the fork's Python lint as upstream's lint-python job runs it (ruff + pyright against dm/tools/lint_python_baseline.tsv), in a WSL venv
set -e
V=$HOME/.bdn-lint-venv
[ -x $V/bin/python ] || { python3 -m venv $V; $V/bin/pip -q install -r "$1/.github/requirements/lint.txt"; }
cd "$1"; $V/bin/python dm/tools/lint_python.py
