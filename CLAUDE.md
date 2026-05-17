# runspec — Claude Code Context

## What this project is

A language-agnostic, TOML-based interface specification for anything runnable.
Runnables (scripts, apps, MCP tools) define their interface in `runspec.toml` or
`pyproject.toml` under `[tool.runspec.<name>]`. The library parses this at runtime,
validates arguments, and exposes a rich `RunSpec` object.

Read `DESIGN.md` for the full design history and rationale.
Read `spec/SPEC.md` for the canonical format specification.

---

## Repository Structure

```
runspec/
  CLAUDE.md                        ← you are here
  DESIGN.md                        ← full design document
  spec/SPEC.md                     ← canonical format specification
  packages/
    python/                        ← active development, reference implementation
      runspec/
        __init__.py                ← public API: parse(), load_spec(), register_type()
        finder.py                  ← locates pyproject.toml or runspec.toml
        loader.py                  ← reads TOML, normalises to internal dict
        inference.py               ← applies inference rules
        types.py                   ← type registry + runspec-python coercers
        validator.py               ← two-pass validation (args then groups)
        parser.py                  ← orchestrates full pipeline, returns RunSpec
        models.py                  ← Arg, Group, RunSpec dataclasses
        errors.py                  ← human-first errors with fuzzy suggestions
        cli.py                     ← discover, check, emit commands
      tests/
        test_inference.py
        test_types.py
        test_validator.py
      pyproject.toml
    node/                          ← stub, not yet implemented
    go/                            ← stub, not yet implemented
  tests/
    integration/
      fixtures/                    ← shared TOML configs all language packs test against
        simple.toml
        complex.toml
  .github/
    workflows/
      python.yml                   ← CI for Python (active)
      node.yml                     ← stub
      go.yml                       ← stub
      integration.yml              ← compliance suite
```

---

## Key Design Decisions

**Format**
- Runnables live directly under `[tool.runspec]` — no intermediate `scripts` key
- `[tool.runspec.greeter]` not `[tool.runspec.scripts.greeter]`
- `[config]` is the only reserved name — everything else is a runnable
- In standalone `runspec.toml`, runnables are top-level: `[greeter]`

**Internally**
- Code uses `runnables` as the dict key (not `scripts`)
- `__script__` on RunSpec refers to the runnable's name — internal naming, not format

**Types**
- Types declared as strings in spec (`"int"`, `"path"`, etc.)
- Coercion handled by language packs — `runspec-python` is bundled with `pip install runspec`
- Custom types registered via `runspec.register_type(name, coercer)`

**Validation**
- Two-pass: individual args first, group constraints second
- Keeps both extensible independently

**Autonomy**
- Defaults to `"confirm"` — safe by default, opt-in to trust
- Resolution order: per-arg → script-level → `[config]` default → library default
- Escalation rule: most restrictive level wins

**Entry points**
- `[project.scripts]` is the preferred convention (PEP 517/518)
- `[tool.poetry.scripts]` supported as fallback with a nudge
- `runspec` binary auto-appears when added as a dependency

---

## Inference Rules (from spec/SPEC.md)

| Condition | Inference |
|---|---|
| `default = 42` | `type = "int"` |
| `default = 3.14` | `type = "float"` |
| `default = "json"` | `type = "str"` |
| `default = false` | `type = "flag"` |
| `options = [...]` | `type = "choice"` |
| No default present | `required = true` |
| `type = "path"` only | `required = true` |

Bool must be checked before int (bool is a subclass of int in Python).

---

## Python Specifics

```bash
# Requirements
Python 3.10+   (tomllib from stdlib on 3.11+; tomli dependency on 3.10)
Zero runtime dependencies on Python 3.11+

# Environment setup
cd packages/python
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
ruff format --check .

# Type check
mypy runspec/
```

---

## Do Not

- Add runtime dependencies to the core library (stdlib only)
- Use `scripts` as a TOML key in runspec format examples
- Change inference rules without updating `spec/SPEC.md` first
- Change the format without updating `spec/SPEC.md` first
- Name internal variables using the format key names (use `runnables`, not `scripts`)

---

## Current Status

Design phase complete. Scaffold in place. Python library implementation in progress.
Node and Go packages are stubs — do not implement them yet.

Focus: get `packages/python/` fully working with all tests passing.

---

## Good Claude Code Prompt Patterns

Be specific and bounded. Examples of good prompts:

```
Read CLAUDE.md. Then look at loader.py and write tests for load_raw
covering both pyproject.toml and runspec.toml formats. Put them in
packages/python/tests/test_loader.py.
```

```
Read CLAUDE.md and inference.py. The infer_arg function needs to handle
the case where both 'type' and 'options' are declared — options should
win and set type to 'choice'. Write the fix and add a test for it.
```

```
Read CLAUDE.md and parser.py. Walk me through what happens step by step
when parse() is called for a script with a subcommand.
```

Avoid open-ended prompts like "build the library" — break work into
one module or one behaviour at a time.
