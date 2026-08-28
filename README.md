# splunk-soar-mcp

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
| `readonly` | 35 | Every query. Cannot change anything. |
| `standard` *(default)* | 41 | ...plus notes, comments, artifacts, container status/severity/owner, custom-list rows. |
| `full` | 48 | ...plus running playbooks and app actions, creating and deleting containers and artifacts, raw POST/DELETE. |

Two further guards:

- **`SOAR_MCP_ALLOWED_LABELS`** — a container-label allowlist. Every write resolves the
  target's label first and refuses if it is not permitted. On a multi-tenant or MSSP
  instance this is what keeps an assistant inside one customer's data.
- **`soar_delete_container`** requires the container's exact name as a second argument and
  refuses if it does not match, so a wrong id cannot delete the wrong case.

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
git clone https://github.com/OWNER/splunk-soar-mcp
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
| `SOAR_MCP_ALLOWED_LABELS` | *(all)* | Comma-separated container labels writes may touch. |
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
| `soar_system_info` | Version, base URL, and this server's mode. Call it first. |
| `soar_list_apps` | Installed apps, filterable by name. |
| `soar_list_app_actions` | The actions an app exposes. |
| `soar_get_app_action` | One action in full — every parameter and output datapath. |
| `soar_list_assets` | Configured assets. |
| `soar_get_asset` | One asset's full configuration. |
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
| `soar_list_action_runs` | App action executions. |
| `soar_get_action_run` | One action's full result, including `result_data`. |

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
| `soar_append_to_custom_list` | standard | Append one row, leaving existing rows alone. |
| `soar_replace_custom_list` | standard | Replace the whole list. |

### Execution — `full` mode only

| Tool | Purpose |
|---|---|
| `soar_run_playbook` | Run a playbook against a container. |
| `soar_run_action` | Run one app action against an asset. |

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
  tools/          platform, playbooks, containers, lists, run, raw, vpe
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
- **Prefer a CA bundle to `SOAR_MCP_VERIFY_SSL=false`.** On-prem SOAR usually ships a
  self-signed certificate; point `SOAR_MCP_CA_BUNDLE` at it rather than disabling
  verification.
- Found a vulnerability? See [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).

Not affiliated with or endorsed by Splunk Inc. "Splunk" and "Splunk SOAR" are trademarks
of Splunk Inc.
