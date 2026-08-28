# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, rather than in a public issue.

Include what an attacker can do, how to reproduce it, and the versions affected.
Expect an initial response within a week.

## Scope

In scope: credential leakage, request forgery against the SOAR instance, bypass of
`SOAR_MCP_MODE` or `SOAR_MCP_ALLOWED_LABELS`, and anything letting a tool call reach an
operation its mode should not permit.

Out of scope, because they are documented behaviour rather than defects:

- **`full` mode is dangerous by design.** It can run playbooks and delete containers.
- **The HTTP transport has no authentication.** It is meant to sit behind a proxy.
- **`soar_rest_post` / `soar_rest_delete` bypass the label allowlist.** They are the
  documented escape hatch, and are registered only in `full` mode.
- **The API token carries the automation user's full permissions.** `SOAR_MCP_MODE`
  shapes what an assistant is offered; the SOAR role is what enforces it.

## Handling credentials

`SPLUNK_SOAR_API` is equivalent to the automation user's password. Keep it in `.env` or a
secret manager — never in the repository, a client config committed to git, or a shell
history. `.env` and `secrets.txt` are gitignored.
