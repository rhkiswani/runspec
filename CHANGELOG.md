# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).

---

## [0.5.0] — 2026-05-18

### Added

- **Recursive dev-mode discovery** — `find_configs_dev()` now walks the full
  directory tree under the `.git` root, not just one level deep. Monorepos
  with `packages/python/mypkg/runspec.toml` layouts are found automatically.
  Skips `.venv`, `__pycache__`, `node_modules`, `dist`, `build`, and all
  hidden directories.

- **`test_finder.py`** — new test file covering `find_config` (walk-up) and
  `find_configs_dev` (recursive scan, skip dirs, multiple configs, no-git
  fallback).

### Changed

- **`runspec.toml` is now the sole supported format.** Support for reading
  runspec configuration from `pyproject.toml` (under `[tool.runspec.*]`) has
  been removed. All docs, specs, and examples updated accordingly.

---

## [0.2.0] — 2026-05-17

### Added

- **`runspec serve`** — starts a live MCP stdio server for the current environment.
  Exposes every runnable as an MCP tool over JSON-RPC 2.0 on stdin/stdout.
  Zero extra dependencies. Connect to Claude Desktop or any MCP-compatible agent
  via `claude_desktop_config.json`.

- **`output` field on runnables** — declares what the runnable writes to stdout.
  Values: `"text"` (default), `"json"` (agent can parse the response),
  `"html"` (reserved for future UI use).
  Surfaces as `x-output` in all emitted schemas.

- **`args.__agent__`** — `RunSpec` now exposes `__agent__: bool`. It is `True`
  when the runnable is called via `runspec serve` (detected from `RUNSPEC_AGENT=1`
  in the environment). Use it to switch output format for agent vs human callers.

- **Installed package discovery** — `runspec discover` now finds packages in the
  current Python environment that list `runspec` as a dependency. Checks package
  data files for a shipped `runspec.toml`, and falls back to `direct_url.json`
  for editable installs.

---

## [0.1.1] — 2026-05-17

### Fixed

- Added `Documentation` URL to PyPI metadata (previously a dead link on the
  project page).

---

## [0.1.0] — 2026-05-17

### Added

Initial release.

- **`runspec.parse()`** — finds config, resolves runnable, parses `sys.argv`,
  validates, coerces, and returns a `RunSpec`.
- **`RunSpec`** — argument namespace with full spec metadata (`__script__`,
  `__source__`, `__command__`, `__autonomy__`, `__spec__`, `__groups__`).
- **`Arg`** — transparent value wrapper; behaves as its native type in all
  expressions (arithmetic, comparison, iteration, path methods).
- **Inference rules** — type and required inferred from defaults and options.
- **Types** — `str`, `int`, `float`, `bool`, `flag`, `path`, `choice`.
- **Validation** — two-pass: individual args first, group constraints second.
- **Groups** — `exclusive`, `inclusive`, `at-least-one`, `exactly-one`,
  `conditional`.
- **Subcommands** — nested command dispatch under a runnable.
- **Autonomy** — per-runnable and per-arg levels; most restrictive wins.
- **`runspec check`** — validates the current project's runspec setup.
- **`runspec discover`** — finds runspec-aware runnables in the local project.
- **`runspec emit`** — emits tool schemas in MCP, OpenAI, or Anthropic format.
- **`register_type()`** — register custom types with a coercer function.
- **`load_spec()`** — loads spec without parsing `sys.argv` (for tooling).
- Python 3.10–3.13 support. Zero runtime dependencies on Python 3.11+.

[0.5.0]: https://github.com/JasonFinestone/runspec/releases/tag/v0.5.0
[0.2.0]: https://github.com/JasonFinestone/runspec/releases/tag/v0.2.0
[0.1.1]: https://github.com/JasonFinestone/runspec/releases/tag/v0.1.1
[0.1.0]: https://github.com/JasonFinestone/runspec/releases/tag/v0.1.0
