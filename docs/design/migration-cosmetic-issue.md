# The sample runnable
It has nested subcommands. In the examples they are 'show' and 'multi' plus 'show'
# What looks fixed:
* sample -r europe -e qa show --symbol VOD.L now parses and runs successfully.
* sample show --help now includes inherited global options (region, env, etc.) plus command options.
* sample -r europe -e qa show --help correctly resolves to command-focused help.
* Parsed object confirms merged args at leaf level (region/env/.../symbol all in selected command spec).
* runspec_command and runspec_command_path are correct (show, ['show']).
# What still looks slightly off (minor UX formatting):
* sample multi show --help usage line currently renders:
  * ... --symbols <str> multi show
* More intuitive order would likely be:
  * ... multi show --symbols <str>
This is mostly a help-string composition issue, not a parsing failure.
So overall: your core parser fixes are working and you

---

## Resolution (0.20.1)

Confirmed and fixed in `packages/python/runspec/runspec/parser.py`.

**Cause:** the help renderer classified args as "command-local" only if they were
declared on the *leaf* command, treating everything else (including args on
*intermediate* commands like `multi`) as inherited globals — so they sorted
before the command path.

**Fix:** only the root runnable's own args are globals. Any arg declared on a
command along the path (intermediate or leaf) is a command arg and renders after
the command path. `_resolve_subcommand` now returns the root global arg names;
`_print_help` splits the usage line and the *Global options* / *Command options*
sections on that rule.

Before: `sample --region <…> --env <…> --symbols <str> multi show [--limit <int>]`
After:  `sample --region <…> --env <…> multi show --symbols <str> [--limit <int>]`

Regression test: `tests/test_parser.py::TestSubcommandGlobals::test_intermediate_command_arg_renders_after_path`.
