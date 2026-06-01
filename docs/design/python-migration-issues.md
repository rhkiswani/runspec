# Runspec Parser Fix Plan for `sample-tool`

## Checklist
- [x] Lock target behavior for command parsing and help output
- [x] Fix command resolution when global flags appear before subcommands
- [x] Fix help rendering so command help shows inherited/global required args
- [x] Add regression tests for all failing CLI flows
- [x] Validate with runspec-only fixture(s) inside this repo
- [x] Confirm no regressions for runnables without commands

## Resolution (Python)

Implemented in `packages/python/runspec/runspec/parser.py` and documented in
`spec/SPEC.md` → *Subcommands → Global (inherited) arguments*.

Decisions locked with the maintainer:
- **Inheritance:** a runnable's top-level args are *global args* every
  subcommand inherits; child args override parent args of the same name.
- **Ordering:** global flags must appear *before* the command token
  (git/docker/argparse style — the most cross-language-portable model).
- **Scope:** Python only this session; Node port tracked in `BACKLOG.md`.

Changes:
- `_resolve_subcommand` now scans argv, keeps global flags (and their values)
  for the parser, and treats the first bare token matching a command name as
  the descent point. It merges `args`/`groups` along the resolved path and
  returns the leaf-local arg names.
- `_print_help` splits inherited globals ("Global options") from the command's
  own args ("Command options") and renders the usage line with globals before
  the command path.
- Regression tests in `tests/test_parser.py::TestSubcommandGlobals` (inline
  `tmp_path` fixtures, matching the repo's existing parser-test style).

## Objective

Make `runspec` correctly handle runnables that define both:
- required top-level args, and
- subcommands (including nested subcommands),

so this works reliably:

- `sample-tool --region ... --env ... show --symbol VOD.L`
- `sample-tool show --help` (should still communicate required globals)
- `sample-tool multi show --help` (should resolve leaf command help)

## Reference Fixture (Runspec-Only)

Use a fixture created under runspec tests (for example `tests/fixtures/parser/subcommands_with_globals/runspec.toml`).
It should define:
- runnable: `[sample-tool]`
- required top-level args: `region`, `env`
- subcommands under `[sample-tool.commands.*]`
- nested subcommands under `[sample-tool.commands.multi.commands.*]`

## Broken Behaviors Observed

1. `sample-tool -r europe -e qa show --symbol VOD.L` fails with unknown args (`show`, `--symbol`).
2. `sample-tool show --help` only shows `--symbol`, hiding required global args.
3. `sample-tool -r ... -e ... show --help` prints root help instead of command-focused help.
4. Nested command help partially works (`multi show --help` resolves leaf usage), but inherited required-global messaging is inconsistent.

## Likely Root Cause (Code)

Primary file:
- `runspec/parser.py`

Key issue:
- `_resolve_subcommand(...)` currently only matches subcommands while `argv[0]` is a command token.
- If argv starts with flags (for example `-r`, `--env`), command resolution stops immediately.
- `_parse_argv(...)` then parses against root args only, and command tokens become unknown.

Secondary issue:
- `_print_help(...)` renders from current selected spec only.
- Command help does not clearly surface inherited/global required args.

## Target Behavior

1. Global flags may appear before command path.
2. Command path is recognized even when globals are present first.
3. Parsing uses effective arg set = global args + selected command args.
4. Help for leaf commands clearly includes required globals inherited from parent scopes.
5. Nested command dispatch remains supported via `args.runspec_command` and `args.runspec_command_path`.

## Implementation Plan (`runspec` Library)

### Phase 1: Command Path Resolution + Arg Partitioning

- Add a parser step that scans argv and identifies command path even if flags appear first.
- Preserve flag/value pairs before and after command tokens.
- Return:
  - selected command path (for example `['multi', 'show']`)
  - selected command spec
  - cleaned argv for arg parsing
  - command tokens removed before `_parse_argv(...)`

### Phase 2: Inherited Args Merge

- Build effective merged arg spec for parsing:
  - root args + each command-level args along selected path.
- Collision policy: child arg definition overrides parent arg with same name.
- Preserve existing normalization behavior (`-` and `_`).

### Phase 3: Help Rendering Semantics

- Root help remains mostly unchanged.
- Command help must include inherited required globals + command-local args.
- Preferred display:
  - either one combined argument list, or
  - separate `Global arguments` and `Command arguments` sections.
- Ensure `sample-tool -r ... -e ... show --help` resolves to `show` help, not root help.

### Phase 4: RunSpec Metadata Integrity

- Keep `__runspec_command_path__` accurate for nested paths.
- Keep public accessors consistent:
  - `runspec_command`
  - `runspec_command_path`
- Keep `__runspec_spec__` as selected leaf command spec (current useful behavior).

### Phase 5: Backward Compatibility

- Do not break runnables without commands.
- Preserve short flag behavior (`short = '-r'`).
- Do not alter coercion, env precedence, or validation behavior except where required for merged args.

## Test Plan

Add parser-level regression tests for:

1. `global flags -> command -> leaf args` parse success.
2. `command -> --help` includes inherited required globals.
3. `global flags -> command -> --help` resolves command help context.
4. Nested `multi show --help` usage correctness.
5. Unknown arg errors still show valid options for selected scope.
6. Mixed ordering forms:
   - `sample-tool --region ... --env ... show --symbol ...`
   - `sample-tool show --symbol ... --region ... --env ...` (explicitly decide expected support)

### Suggested New Fixtures

- `tests/fixtures/parser/subcommands_with_globals/runspec.toml`
- `tests/fixtures/parser/subcommands_with_globals/expected_help_root.txt`
- `tests/fixtures/parser/subcommands_with_globals/expected_help_show.txt`
- `tests/fixtures/parser/subcommands_with_globals/expected_help_multi_show.txt`

## Acceptance Criteria

- `sample-tool -r europe -e qa show --symbol VOD.L` parses successfully.
- `sample-tool show --help` communicates required globals (`region`, `env`) if still required by design.
- `sample-tool -r europe -e qa show --help` returns command-focused help.
- `sample-tool multi show --help` returns leaf-specific help with correct inherited requirements.
- No regressions for runnables without commands.

## Notes for Agent

- This task is **runspec-only**. Do not assume access to downstream app repositories.
- Patch targets are inside this repo only:
  - `runspec/parser.py`
  - related tests under `tests/`
- Build and validate exclusively with in-repo fixtures.
- Keep examples generic (`sample-tool`, `sample_app`) and avoid company/product naming.
