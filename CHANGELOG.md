# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Administration reads: `soar_get_system_settings` (34 sections, with a guide to
  which admin page each backs), `soar_get_license`, `soar_get_system_health`,
  `soar_list_cluster_nodes`, `soar_list_feature_flags`, `soar_list_ingestion_status`.
- Event metadata: `soar_list_container_statuses`, `soar_list_severities`,
  `soar_list_custom_fields`, `soar_list_cef_fields`, `soar_list_workbooks`,
  `soar_get_workbook`.
- Users and roles: `soar_list_users`, `soar_get_user`, `soar_list_roles`,
  `soar_get_role` with its permission matrix, plus `soar_create_role`,
  `soar_update_role` and `soar_delete_role` in `full` mode. Platform built-in
  roles are refused, and deletion requires the role's exact name.
- Custom list lifecycle: `soar_create_custom_list`, `soar_update_custom_list_row`
  (a targeted row replacement rather than rewriting the list), and
  `soar_delete_custom_list` in `full` mode.

### Fixed

- `soar_add_comment` posted to `container/<id>`, which SOAR answers with
  `{"success": true}` while silently creating nothing. It now posts to
  `container_comment`, verified against 7.1.
- `soar_get_playbook_run_log` no longer falls back to `playbook_run_log`, an
  endpoint that returns `403 Not allowed`; an empty log now reports the run's
  status, since a run still executing has not written one yet.
- httpx no longer logs one INFO line per REST call into the client's log pane.

### Security

- Credentials are stripped from every response. SOAR returns asset configuration
  verbatim, including populated `password`, `client_secret`, `api_key` and
  `ph auth token` fields; these are now replaced before anything leaves the
  process, including via `soar_rest_get` and error bodies.
- `SOAR_MCP_ALLOWED_LABELS` now gates reads as well as writes, and container
  listings are filtered to permitted labels server-side.
- Refusals no longer name the target's container label or the permitted set, and
  `soar_system_info` reports only a count. On a multi-tenant instance the
  allowlist is the customer list, so echoing it let a caller enumerate tenants.

### Changed

- Credentials come from the environment or an env file only. The bespoke
  `secrets.txt` search was removed; `SOAR_MCP_ENV_FILE` overrides the env file
  path, which a stdio server usually needs since it inherits its client's
  working directory.
- Every tool that reaches the instance is now annotated `open_world_hint=True`;
  only the local block builders are closed-world.

## [0.1.0]

Initial release.

### Added

- Read tools for apps, assets, app actions, custom functions and repositories.
- Playbook tools: listing, metadata, block inventory, per-block source, run history,
  run logs with a substring filter, and app action runs with full `result_data`.
- Container tools: listing with label/status/severity/owner filters, artifacts, notes
  and comments.
- Custom list tools: listing, contents, append and replace.
- Execution tools for running playbooks and app actions, in `full` mode.
- Visual editor block tools: decode and encode clipboard payloads, and builders for
  code, action, decision, format, custom function and child playbook blocks.
- Raw REST escape hatches, with POST and DELETE gated to `full` mode.
- Three-tier safety model (`readonly` / `standard` / `full`) that decides which tools are
  registered, plus a container-label allowlist enforced on every write.
- Resources for the `phantom.*` callable reference, datapath forms and the editor block
  format; prompts for debugging a run, triaging a container and designing a block.
- stdio and streamable-HTTP transports.
