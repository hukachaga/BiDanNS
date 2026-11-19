# Banana Native's GitHub workflows (off in BigDanNS)

These are upstream's workflows from before the repository moved to git.eden-emu.dev. GitHub only runs files in `.github/workflows/`, so here they are kept for reference and do not run:

- `tests.yml` and `lint-c.yml` need upstream's self-hosted macOS runner (`runs-on: xcode-27`), which a fork does not have, so every push to `main` failed or stayed queued;
- `lint-python.yml` reports 336 findings that are not in its baseline, all in upstream files of v0.3.45 and none in `bigdanns/`;
- `fuzz.yml` ran on a schedule.

To check a change the way upstream does, run their steps by hand (`CONTRIBUTING.md`, "Checking a change"), or run `bigdanns/tools/lint_wsl.sh` for the Python lint.
