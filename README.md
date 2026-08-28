# splunk-soar-mcp

[![PyPI](https://img.shields.io/pypi/v/splunk-soar-mcp)](https://pypi.org/project/splunk-soar-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/splunk-soar-mcp)](https://pypi.org/project/splunk-soar-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

An [MCP](https://modelcontextprotocol.io) server for **Splunk SOAR** (formerly Phantom).

It gives an AI assistant a first-class view of a SOAR instance — apps, assets, playbooks,
containers, artifacts, custom functions and custom lists — plus the two things that
actually make SOAR work go faster: **playbook run logs** for debugging, and a **visual
editor block generator** that emits payloads you paste straight onto the playbook canvas.

```
You:  why did playbook run 88214 fail?
       → soar_get_playbook_run_log(88214)
       → soar_get_playbook_source("Triage", block="build_digest")
      The format block reads cf_lookup:custom_function:result, but cf_lookup is a
      custom function block — that form is the code-block shape. It needs
      cf_lookup:custom_function_result.data.result.
```

---

## Contents

- [Why](#why)
- [Safety model](#safety-model)
- [Install](#install)
- [Configure](#configure)
- [Connect a client](#connect-a-client)
- [Tools](#tools)
- [Resources and prompts](#resources-and-prompts)
- [HTTP transport](#http-transport)
- [Development](#development)
- [Security](#security)

---

## Why

The SOAR REST API is capable but awkward: filter values need literal quotes inside the
query string, half the useful data hangs off endpoints you have to know the name of, and
the clipboard format the playbook editor uses is not documented anywhere. This server
wraps all of that so an assistant can answer real questions — *which asset does this
action run against, what did that run actually return, why did this block fail* — without
a REST call being hand-written each time.

Three things it does that a generic REST wrapper does not:

- **Run logs, sliced.** `soar_get_playbook_run_log` pulls the full debug log for one run
  and greps it, so a failing block is one call away rather than a scroll through the UI.
- **Playbook source by block.** `soar_get_playbook_source(pb, block="format_1")` returns
  one function instead of a 2000-line file — the generated python is the ground truth for
  block names and datapaths.
- **Paste-able editor blocks.** `soar_build_*` emits the base64 the playbook editor
  accepts, with the fields the editor silently rejects a node for omitting already filled
  in. `soar_decode_vpe_block` goes the other way, so you can learn a node's real shape by
  copying a working block out of the UI.

## Safety model

> **Read this first.** These modes are **guardrails, not a security boundary.** They stop
> an assistant from wandering; they stop nobody who holds the API token, because that
> person can bypass this server with one `curl`. **The only enforcement that actually
> holds is the SOAR role on the automation user whose token you configured.** Scope that
> role to the job, and treat everything below as defence in depth on top of it.

`SOAR_MCP_MODE` decides which tools are **registered**, not merely which ones refuse when
called. A `readonly` server does not expose a single mutating tool, so nothing can be
talked into using one.

| Mode | Tools | What it can do |
|---|---:|---|
| `readonly` | 51 | Every query, administration included. Cannot change anything. |
| `standard` *(default)* | 59 | ...plus notes, comments, artifacts, container status/severity/owner, and custom lists. |
| `full` | 70 | ...plus running playbooks and app actions, creating and deleting containers, lists and roles, raw POST/DELETE. |

Two further guards:

- **`SOAR_MCP_ALLOWED_LABELS`** — a container-label allowlist, applied to reads and
  writes alike. On a multi-tenant or MSSP instance this is what keeps an assistant inside
  one customer's data. See [Tenant scoping](#tenant-scoping).
- **`soar_delete_container`** requires the container's exact name as a second argument and
  refuses if it does not match, so a wrong id cannot delete the wrong case.

### Credential redaction

SOAR's REST API returns asset configuration verbatim, **credentials included** —
`/rest/asset` hands back populated `password`, `client_secret`, `api_key` and
`ph auth token` fields in plaintext. Anything this server returns may be read by a
language model, written to a transcript and retained by whoever runs that model, so
every response is scrubbed before it leaves the process:

```
soar_get_asset("prod_edr")
  name           prod_edr
  base_url       https://api.example.com
  client_secret  «redacted by splunk-soar-mcp»
```

Redaction is keyed on the *field name*, not the value — guessing at values both misses
real secrets and destroys legitimate data like file hashes. It runs at the single point
every tool serialises through, covers `soar_rest_get` and error bodies as well as the
typed tools, and is not configurable off.

It is a safety net, not a licence: scope the automation user so it cannot read what it
does not need.

### Tenant scoping

`SOAR_MCP_ALLOWED_LABELS` gates **reads as well as writes**. Container listings are
filtered to the permitted labels server-side, and fetching a container, its artifacts,
notes or comments outside that set is refused — on a scoped deployment, reading another
tenant's case is the disclosure, not just changing it.

Refusals name neither the target's label nor the permitted set, and `soar_system_info`
reports only how many labels are permitted. On a multi-tenant instance the allowlist *is*
the customer list, and an error message is an answer: without this, repeated calls would
enumerate every tenant the deployment knows about.

### Running it for more than one person

If several people or roles share an instance, do **not** try to express that with one
server and application-level checks. Run **one process per role, each with its own SOAR
automation user**:

| Process | `SOAR_MCP_MODE` | SOAR automation user's role |
|---|---|---|
| analyst | `full` | view/edit containers, run playbooks, scoped to their tenants |
| engineer | `readonly` | read-only across the instance |
| dashboard | `readonly` | read-only, one tenant |

The isolation that matters there is not this server's mode — it is that each process holds
a **differently privileged credential**. If the layer above is compromised, prompt-injected
or simply wrong, SOAR still refuses the call. A single process with in-code role checks
gives you none of that, because it holds one token that can do everything any role can do.

Three rules for that deployment:

- The SOAR token never reaches a browser, and this server is never reachable from the
  internet.
- Authenticate your users at your own application, not here — MCP's OAuth support secures
  the *service-to-service* hop, not end-user login.
- Anything irreversible — containment, isolation, blocking — gets an explicit human
  confirmation, not an assistant's decision. Container data is attacker-controlled text,
  so prompt injection against a SOAR assistant is a realistic threat, not a theoretical one.

## Install

```bash
# with uv (recommended — no virtualenv to manage)
uvx splunk-soar-mcp --help

# or with pip
pip install splunk-soar-mcp

# or from source
git clone https://github.com/huseynAgazade/splunk-soar-mcp
cd splunk-soar-mcp
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Configure

Set these in the environment, in the `env` block of your MCP client's server config, or
in an env file (copy `.env.example` to `.env`).

| Variable | Default | Meaning |
|---|---|---|
| `SPLUNK_SOAR_URL` | *required* | Base URL, e.g. `https://soar.example.com`. A trailing `/rest` is stripped. |
| `SPLUNK_SOAR_API` | *required* | Automation user token (`ph-auth-token`). |
| `SOAR_MCP_ENV_FILE` | `.env` | Path to the env file to read. A stdio server inherits its working directory from its client, so an absolute path here is usually what you want. |
| `SOAR_MCP_MODE` | `standard` | `readonly`, `standard` or `full`. |
| `SOAR_MCP_ALLOWED_LABELS` | *(all)* | Comma-separated container labels this server may read or write. |
| `SOAR_MCP_VERIFY_SSL` | `true` | Set `false` only for self-signed certs on a trusted network. |
| `SOAR_MCP_CA_BUNDLE` | — | Path to a CA bundle. Preferred over disabling verification. |
| `SOAR_MCP_TIMEOUT` | `60` | Per-request timeout, seconds. |
| `SOAR_MCP_DEFAULT_PAGE_SIZE` | `25` | Default rows per listing. |
| `SOAR_MCP_MAX_PAGE_SIZE` | `500` | Ceiling on `page_size`. |

Get a token in the SOAR UI under **Administration → User Management → Automation Users**.
Give that user the narrowest role that covers your chosen mode.

Check the configuration without starting a server:

```bash
splunk-soar-mcp --list-tools           # what this configuration exposes
splunk-soar-mcp --list-tools --mode readonly
```

## Connect a client

### Claude Code

```bash
claude mcp add splunk-soar \
  --env SPLUNK_SOAR_URL=https://soar.example.com \
  --env SPLUNK_SOAR_API=your-token \
  --env SOAR_MCP_MODE=standard \
  -- uvx splunk-soar-mcp
```

### Claude Desktop / any stdio client

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "splunk-soar": {
      "command": "uvx",
      "args": ["splunk-soar-mcp"],
      "env": {
        "SPLUNK_SOAR_URL": "https://soar.example.com",
        "SPLUNK_SOAR_API": "your-token",
        "SOAR_MCP_MODE": "standard"
      }
    }
  }
}
```

Installed with `pip` instead of `uv`? Use `"command": "splunk-soar-mcp"` and drop `args`.

## Tools

### Discovery — what the instance has

| Tool | Purpose |
|---|---|
| `soar_system_info` | Instance version, base URL, this server's mode and label scope. Call it first. |
| `soar_list_apps` | Installed apps, filterable by name. |
| `soar_list_app_actions` | The actions an app exposes. |
| `soar_get_app_action` | One action in full — every parameter and output datapath. |
| `soar_list_assets` | Configured assets. |
| `soar_get_asset` | One asset's full configuration, credentials redacted. |
| `soar_list_custom_functions` | Custom functions available to playbooks. |
| `soar_get_custom_function` | One custom function, with its inputs, outputs and source. |
| `soar_list_repos` | Source-control repositories. |

### Playbooks and runs

| Tool | Purpose |
|---|---|
| `soar_list_playbooks` | Playbooks, filterable by name, label, or active-only. |
| `soar_get_playbook` | Metadata and block inventory. |
| `soar_list_playbook_blocks` | Block names and signatures, cheaply. |
| `soar_get_playbook_source` | Generated python — whole file, or one block. |
| `soar_list_playbook_runs` | Run history, filterable by playbook, container or status. |
| `soar_get_playbook_run` | One run's full record. |
| `soar_get_playbook_run_log` | **The debug log for one run**, with a substring filter. |
| `soar_list_action_runs` | App action executions, failures included. |
| `soar_get_action_run` | One action run plus the per-asset executions beneath it. |

**On logs.** There are two different things here, and only one of them is a log.

*Playbook runs* have a real debug log — every `phantom.debug` line, block transition and
traceback — read with `soar_get_playbook_run_log`.

*Actions* have no debug log; `action_run/<id>/log` and `app_run/<id>/log` both return 400.
What they have instead is **history**, which is what the UI's Action Run page shows and
what `soar_list_action_runs` returns: newest first, with the action, its status and
message, the container and playbook run, and — via the `_annotation_playbook_run_effective_user`
annotation — **the user each action ran as**. That last column is what makes it an audit
trail rather than a list of anonymous events, and it is how you tell automation apart from
a specific service account.

For one action's detail, `soar_get_action_run` returns the `action_run` (status, message)
together with the `app_run`s beneath it (`exception_occured`, `result_summary`,
`result_data`). On a failure `result_data` is `null`, so the `message` is what to read; if
the action ran inside a playbook, the fuller reason is in that playbook's run log.

### Containers and artifacts

| Tool | Mode | Purpose |
|---|---|---|
| `soar_list_containers` | read | Containers, filterable by name, label, status, severity, owner. |
| `soar_get_container` | read | One container, with its custom fields. |
| `soar_list_artifacts` | read | A container's artifacts. |
| `soar_get_artifact` | read | One artifact, with every CEF field. |
| `soar_list_notes` | read | Notes on a container. |
| `soar_list_comments` | read | Comments on a container. |
| `soar_add_comment` | standard | Add a comment. |
| `soar_add_note` | standard | Add a titled note. |
| `soar_update_container` | standard | Change status, severity, sensitivity, owner, name or description. |
| `soar_add_artifact` | standard | Add an artifact, with CEF fields. |
| `soar_create_container` | full | Create a container. |
| `soar_delete_artifact` | full | Delete an artifact. |
| `soar_delete_container` | full | Delete a container — requires its exact name to confirm. |

### Custom lists

| Tool | Mode | Purpose |
|---|---|---|
| `soar_list_custom_lists` | read | Custom lists (`decided_list`). |
| `soar_get_custom_list` | read | One list's contents as a grid. |
| `soar_create_custom_list` | standard | Create a list, optionally with initial rows. |
| `soar_append_to_custom_list` | standard | Append one row, leaving existing rows alone. |
| `soar_update_custom_list_row` | standard | Replace one row by index — the surgical option. |
| `soar_replace_custom_list` | standard | Replace the whole list. |
| `soar_delete_custom_list` | full | Delete a list — requires its exact name to confirm. |

### Administration

Read-only by design. The administration surface holds an instance's credentials and
tenant arrangements; a misconfigured SMTP relay or authentication setting is not
something an assistant should be able to change by accident.

| Tool | Purpose |
|---|---|
| `soar_get_system_settings` | Instance settings by section — company info, ROI, email, forwarders, credential management, playbook execution, authentication, account security, debug levels, audit-trail config, clustering, FIPS, multi-tenancy. Call it bare to list the 34 sections and which admin page each backs. |
| `soar_get_license` | Licence status, entitlements and current usage. |
| `soar_get_system_health` | Service states plus load, memory, swap, database and vault utilisation. |
| `soar_list_cluster_nodes` | Cluster members. Empty on a single node. |
| `soar_list_feature_flags` | Platform feature flags and their values. |
| `soar_list_ingestion_status` | Ingestion runs per asset — finds an on-poll integration that stopped. |

### Event metadata

The vocabulary a playbook works in. Reading these is what stops a block being written
against a status or field that does not exist on the instance.

| Tool | Purpose |
|---|---|
| `soar_list_container_statuses` | Configured statuses — the values `soar_update_container` accepts. |
| `soar_list_severities` | Configured severities, with display order and colour. |
| `soar_list_custom_fields` | Container custom fields and their types. |
| `soar_list_cef_fields` | CEF field definitions and what each `contains`. |
| `soar_list_workbooks` | Workbook templates. |
| `soar_get_workbook` | One workbook's phases and tasks, in order. |

### Users and roles

| Tool | Mode | Purpose |
|---|---|---|
| `soar_list_users` · `soar_get_user` | read | Platform users and their roles. |
| `soar_list_roles` | read | Roles. `immutable` marks a platform built-in. |
| `soar_get_role` | read | One role's full permission matrix. |
| `soar_create_role` | full | Create a role. Unspecified verbs default to `deny`. |
| `soar_update_role` | full | Change name, description or permissions. |
| `soar_delete_role` | full | Delete a role — exact name required to confirm. |

Permission areas: `apps`, `assets`, `automation_broker`, `case_management`, `containers`,
`custom_lists`, `onprem_automation`, `playbooks`, `system_settings`, `users_roles`,
`workbooks`. Verbs: `view`, `edit`, `delete`, `execute`.

Two guards on role management: platform built-ins (`immutable: true`) are refused
outright, and deletion requires the role's exact name. Note that SOAR **soft-deletes**
roles — the role is disabled and leaves the listing, but the record stays fetchable by id
and a second delete returns 404.

### Execution — `full` mode only

| Tool | Purpose |
|---|---|
| `soar_run_playbook` | Run a playbook against a container. Returns a `playbook_run_id`. |
| `soar_run_action` | Run one app action against an asset. Returns an `action_run_id`. |

Both are asynchronous: they queue the work and return an id. Poll it with
`soar_get_playbook_run` / `soar_get_action_run`, and read `soar_get_playbook_run_log`
for the detail. A response saying the run *started* is not a response saying it
succeeded.

These perform real automation — containment, blocking, notification. Confirm with an
operator before calling them.

### Visual editor blocks — local, never touches the instance

| Tool | Purpose |
|---|---|
| `soar_decode_vpe_block` | Decode a payload copied out of the playbook editor. |
| `soar_encode_vpe_block` | Encode a raw envelope. |
| `soar_build_code_block` | Custom Code block — the code is compiled first, so syntax errors surface here. |
| `soar_build_action_block` | App action block. |
| `soar_build_decision_block` | Decision block, with the `else` branch the editor requires. |
| `soar_build_format_block` | Format block. |
| `soar_build_custom_function_block` | Custom function (utility) block. |
| `soar_build_playbook_block` | Child playbook block. |

### Raw REST

| Tool | Mode | Purpose |
|---|---|---|
| `soar_rest_get` | read | GET any `/rest` path. |
| `soar_rest_post` | full | POST any `/rest` path. Bypasses the label allowlist. |
| `soar_rest_delete` | full | DELETE any `/rest` path. |

## Resources and prompts

Resources:

| URI | Contents |
|---|---|
| `soar://reference/phantom-api` | Every callable on the `phantom` object inside a running block, grouped by purpose. |
| `soar://reference/datapaths` | How each block type's output is read downstream, and which forms fan out. |
| `soar://reference/vpe-blocks` | The editor clipboard format and the fields it rejects a node for omitting. |
| `soar://instance/summary` | Live counts of apps, assets, playbooks, lists and containers. |

Prompts: `debug_playbook_run`, `triage_container`, `design_block`.

## HTTP transport

For a shared deployment:

```bash
splunk-soar-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

The endpoint is `/mcp`. **The server carries no authentication of its own** — anyone who
can reach the port inherits the API token's permissions. Put it behind an authenticating
proxy, bind it to a private interface, and run it in `readonly` unless you have a reason
not to.

## Development

```bash
pip install -e ".[dev]"
pytest                          # no live instance needed — the REST layer is mocked
ruff check .
python scripts/smoke_test.py    # drives the server over stdio as a real MCP client
python scripts/smoke_test.py --live   # ...and calls the configured instance
```

To exercise every registered tool against a real instance and get a coverage
report of what was and was not called:

```bash
python scripts/test_all_tools.py                    # local builders + all reads
python scripts/test_all_tools.py --write            # + writes, confined to --label
python scripts/test_all_tools.py --write --full     # + create/delete, self-cleaning
python scripts/test_all_tools.py --write --full --execute \
    --playbook "My Playbook" --action "geolocate ip" --asset maxmind
```

Writes are confined to `--label` (default `test_label`) and every object the
script creates, it deletes.

Layout:

```
src/splunk_soar_mcp/
  config.py       settings, credential resolution, the mode enum
  client.py       async REST client — auth, pagination, SOAR's filter syntax
  app.py          shared runtime state, the label allowlist guard
  server.py       builds the server, registers tools per mode
  formatting.py   compact table rendering
  redaction.py    strips credentials from every response
  tools/          platform, playbooks, containers, lists, admin, metadata,
                  users, run, raw, vpe
  vpe/blocks.py   clipboard payload codec and node builders
  reference/      the markdown served as resources
scripts/smoke_test.py       an example MCP client
scripts/test_all_tools.py   exhaustive tool exerciser with a coverage report
```

Adding a tool: write it in the right `tools/` module with a `@mcp.tool` decorator, a
docstring whose `Args:` section documents each parameter, and a `ToolAnnotations` that
tells the truth about whether it mutates. Register it in `server.py` under the lowest mode
that should have it. Raise `SoarError` for anything the caller could act on — its message
reaches the model, where a plain exception would be masked.

## Security

- **Never commit credentials.** `.env` is gitignored. The token is equivalent to the
  automation user's full permissions.
- **Scope the automation user's role** to the mode you run in. `SOAR_MCP_MODE` shapes what
  the assistant is offered; the SOAR role is what actually enforces it.
- **Use `SOAR_MCP_ALLOWED_LABELS` on multi-tenant instances.** It is the difference between
  an assistant that can comment on one customer's cases and one that can comment on all of
  them.
- **On self-signed certificates.** On-prem SOAR usually ships one. If it is signed by a CA
  you control, point `SOAR_MCP_CA_BUNDLE` at that CA and keep verification on. If it is
  self-signed by the appliance itself, pinning it often *cannot* work: SOAR's default
  certificate carries no Authority Key Identifier, and Python 3.13+ enables
  `ssl.VERIFY_X509_STRICT` by default, which rejects such a certificate as its own CA even
  though OpenSSL accepts the chain. In that case `SOAR_MCP_VERIFY_SSL=false` on a trusted
  network is the honest option — the alternative is a CA bundle that silently does nothing.
- Found a vulnerability? See [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).

Not affiliated with or endorsed by Splunk Inc. "Splunk" and "Splunk SOAR" are trademarks
of Splunk Inc.
