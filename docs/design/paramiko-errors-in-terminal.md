# paramiko "Error reading SSH protocol banner" in the launching terminal

## Symptom

When launching `runspec-console` from a terminal, paramiko tracebacks like the
one below periodically spill into that terminal — sometimes seemingly with no
user activity. The full original capture is in the [appendix](#appendix-original-capture).

```
ERROR: Exception (client): Error reading SSH protocol banner
ERROR: ...
ERROR:     raise socket.timeout()
ERROR: TimeoutError
ERROR: ...
ERROR: paramiko.ssh_exception.SSHException: Error reading SSH protocol banner
```

## Diagnosis

This is a **connection-setup** failure, not an idle / mid-stream disconnect.
"Error reading SSH protocol banner" means the TCP socket opened, but the
server's `SSH-2.0-…` identification banner did not arrive before paramiko's
banner-read timeout elapsed (`socket.timeout` → `TimeoutError`, re-raised as
`SSHException`).

Two factors combine:

1. **Tight, implicit timeouts.** `executor._make_ssh_client` connected with only
   `timeout=10` (the TCP-connect timeout) and never set paramiko's
   `banner_timeout` / `auth_timeout`, leaving them at paramiko's default ~15s.
   That is easily exceeded by a slow server, reverse-DNS-on-connect
   (`sshd UseDNS`), VPN/proxy latency, or a server throttling new connections
   (`sshd MaxStartups`).

2. **A self-generated connection storm.** `Bridge._refresh_cycle` runs every
   30s and, *concurrently for every host*, opens a fresh SSH connection for a
   connectivity probe (`ssh host true`) and then **another** for runnable
   discovery. With several hosts this is a burst of simultaneous fresh
   handshakes every 30s for the whole session — exactly the pattern that trips
   `sshd MaxStartups` and makes the server drop/stall new connections right
   before sending the banner. This is why the errors appear "with no activity":
   the activity is the background refresh.

Separately, the **noise itself** was worse than it needed to be: paramiko's
transport thread logs the full traceback at `ERROR` *before*
`_make_ssh_client` catches and re-surfaces the exception. With no logging
handler configured, those records hit Python's last-resort handler and printed
straight to the launching terminal — even though the code "handles" the failure.

## What was built (v0.5.0)

Scope chosen: **visibility + mitigation** (the 30s refresh-storm rework is
noted below as follow-up, deliberately out of scope here).

### Visibility — capture paramiko logs into the Dev tab

- `Bridge` installs `_ParamikoDevHandler` on the `paramiko` logger. Each record
  is forwarded to the frontend as a `runspec:ssh` event carrying `level`,
  `logger`, `message`, and (when present) the formatted `traceback`.
- Propagation on the `paramiko` logger is turned **off**, so the raw tracebacks
  no longer leak to the launching terminal — they live in the app instead.
- The Dev tab gains an `ssh` category (filter chip + colour). `ERROR` records
  render red and count toward the error tally; rows are expandable to show the
  full banner-timeout stack.
- Capture is `INFO` by default and widens to `DEBUG` (packet/kex detail) when
  started with `--dev` / `--devtools`.

### Mitigation — explicit, tunable connect timeouts

- `_make_ssh_client` now sets `banner_timeout=30` and `auth_timeout=30` (and an
  explicit `connect_timeout=10`) instead of relying on paramiko's defaults.
- All three are overridable via `[ssh]` in `config.toml`:

  ```toml
  [ssh]
  connect_timeout = 10
  banner_timeout  = 30
  auth_timeout    = 30
  ```

## Follow-up (not done here)

The root cause of the *frequency* is the refresh storm. A deeper fix would back
off / serialize / reuse SSH connections in `_refresh_cycle` (e.g. a single
multiplexed connection per host, or a longer interval with jitter) so the
console stops hammering `sshd` every 30s. Tracked separately.

---

## Appendix: original capture

```
(venv-runspec-console) finestoj@LONWL048262:Projects$ runspec-console
ERROR: Exception (client): Error reading SSH protocol banner
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\venv-runspec-console\Lib\site-packages\paramiko\transport.py", line 2213, in _check_banner
ERROR:     buf = self.packetizer.readline(timeout)
ERROR:   File "C:\Users\finestoj\Projects\venv-runspec-console\Lib\site-packages\paramiko\packet.py", line 395, in readline
ERROR:     buf += self._read_timeout(timeout)
ERROR:            ~~~~~~~~~~~~~~~~~~^^^^^^^^^
ERROR:   File "C:\Users\finestoj\Projects\venv-runspec-console\Lib\site-packages\paramiko\packet.py", line 673, in _read_timeout
ERROR:     raise socket.timeout()
ERROR: TimeoutError
ERROR:
ERROR: During handling of the above exception, another exception occurred:
ERROR:
ERROR: Traceback (most recent call last):
ERROR:   File "C:\Users\finestoj\Projects\venv-runspec-console\Lib\site-packages\paramiko\transport.py", line 2029, in run
ERROR:     self._check_banner()
ERROR:     ~~~~~~~~~~~~~~~~~~^^
ERROR:   File "C:\Users\finestoj\Projects\venv-runspec-console\Lib\site-packages\paramiko\transport.py", line 2217, in _check_banner
ERROR:     raise SSHException(
ERROR:         "Error reading SSH protocol banner" + str(e)
ERROR:     )
ERROR: paramiko.ssh_exception.SSHException: Error reading SSH protocol banner
```
