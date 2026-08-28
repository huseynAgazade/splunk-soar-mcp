# `phantom.*` callable reference — SOAR 7.1.0.225

Complete list of callables on the `phantom` object (`phantom.rules`) as seen **inside a
running playbook block** on a SOAR 7.1 instance. Captured 2026-07-31 with:

```python
    methods = [name for name in dir(phantom) if callable(getattr(phantom, name))]
    for method in methods:
        phantom.debug(method)
```

**This is a ground-truth dump, not documentation.** It proves a name *exists*; it does not
give signatures. Before using an unfamiliar one, check it against a real playbook or CF on
the instance (`soar_get_playbook_source`), or probe it in
a scratch code block.

Names with a **leading or trailing `_`** are internal — they work, but they are undocumented
and free to change between platform versions. `_do_request_get` is the notable exception:
it is used throughout a SOAR 7.1 instance's custom functions and is effectively load-bearing.

The same namespace is available inside **custom functions** after `import phantom.rules as
phantom`, and inside **playbook code blocks** with no import at all.

---

## REST and HTTP

| Callable | Notes |
|---|---|
| `_do_request_get` / `_do_request_post` / `_do_request_delete` | Hits `/rest/<endpoint>`. Returns `(ok, msg, json)`. The workhorse. Returns `(ok, msg, json)`. |
| `session_get` / `session_post` / `session_delete` | Full URL, uses the platform session. **Reaches non-`/rest/` UI endpoints** (e.g. `ingestion_history_data`) that reject API-token auth with 403. |
| `get_default_rest_headers` | Pair with `session_*`. |
| `get_base_url` | ✅ confirmed present. Returns the instance URL — do not hardcode an IP. |
| `get_rest_base_url`, `build_phantom_rest_url` | Variants; `build_phantom_rest_url(path)` returns `…/rest/<path>`. |
| `get_request_iter_pages`, `_rest_list_iterator` | Pagination helpers (the latter is the lower-level one). |
| `get_user_session_token`, `get_phantom_home` | |

## Containers and artifacts

`create_container` · `get_container` · `update` · `promote` · `close` · `set_label` ·
`set_severity` · `set_sensitivity` · `set_status` · `_set_status` · `set_owner` ·
`set_incident_owner` · `add_artifact` · `save_artifact` · `delete_artifact` ·
`get_artifacts` · `get_artifact_ids_from_action_result` · `get_tagged_artifacts` ·
`artifact_values` · `add_tags` · `remove_tags` · `get_tags` · `get_cef_data` ·
`get_cef_value` · `get_datapaths_for_contains` · `collect_from_container` ·
`collect_from_contains` · `get_current_container_id_` · `get_current_container_label_` ·
`_get_container_id_from_user_input`

## Notes, comments, attachments, pins

`add_note` · `get_notes` · `add_comment` · `comment` · `add_attachment` ·
`delete_attachment` · `pin` · `update_pin` · `delete_pin`

## Playbook control and blocks

`playbook` · `playbook_block` · `act` · `decision` · `condition` · `format` ·
`get_format_data` · `save_block_result` · `get_block_result` · `custom_function` ·
`get_custom_function_results` · `get_custom_function_status` · `is_custom_function_running` ·
`get_playbook_results` · `get_playbook_status` · `get_playbook_info` ·
`get_current_playbook_info` · `get_child_playbook_results` ·
`get_child_playbook_action_results` · `get_parent_playbook_run_id` · `get_playbook_run_id_` ·
`get_playbook_scope_` · `get_playbook_scope_artifacts_` · `call_playbook_action_callback` ·
`call_playbook_custom_function_callback` · `playbooks_completed` · `runs_completed` ·
`actions_done` · `non_started_runs` · `completed` · `discontinue` · `set_action_limit` ·
`get_collect_limit_` · `set_collect_limit_` · `get_parent_handle` · `set_parent_handle`

## Collecting data

`collect` · `collect2` · `collect_for_condition` · `collect_from_action_result` ·
`collect_from_playbook_results` · `get_action_results` · `get_action_status` ·
`get_action_info` · `get_successful_action_results_v2` · `get_filtered_data` ·
`get_summary` · `get_raw_data` · `get_results` · `extract_data_paths` ·
`_extract_data_path` · `expand_datapaths_` · `fix_datapath` · `fix_artifact_dp` ·
`get_value` · `get_req_value` · `get_str_val` · `get_json_object` · `dump_json` ·
`_merge_jsons` · `merge` · `join` · `concatenate`

## State and storage

`save_run_data` · `get_run_data` · `save_data` · `get_data` · `clear_data` ·
`save_object` · `get_object` · `clear_object` · `get_extra_data` ·
`save_playbook_output_data` · `datastore_add` · `datastore_check` · `datastore_delete` ·
`datastore_get` · `datastore_present` · `datastore_set` · `_save_data_datastore` ·
`_get_data_datastore` · `_clear_data_datastore` · `_save_data_filesystem` ·
`_get_data_filesystem` · `_clear_data_filesystem` · `escape_db_key` · `unescape_db_key`

The `datastore_*` family is a cross-run key/value store — a cleaner dedup/suppression
backing than a custom list when the data is not meant to be human-edited.

## Custom lists

`get_list` · `add_list` · `set_list` · `remove_list` · `check_list` · `delete_from_list` ·
`get_list_from_string`

## Vault

`vault_add` · `vault_delete` · `vault_info` · `get_vault_file` · `get_vault_file_path` ·
`get_vault_item_info` · `Vault`

## Prompts, tasks, phases, workbooks

`prompt` · `prompt2` · `task` · `add_task` · `get_tasks` · `get_incident_task` ·
`get_incident_tasks` · `set_task_owner` · `get_task_notes` · `add_workbook` · `get_phase` ·
`set_phase` · `get_incident_phase` · `set_incident_phase` · `_get_phase_data_from_user_input` ·
`add_response_plan` · `add_response_plan_task` · `get_response_templates` · `set_duetime` ·
`assign` · `_get_template_id_from_user_input` · `_get_statuses_for_status_type`

## Validators and type helpers

`is_domain` · `is_email` · `is_hash` · `is_hostname` · `is_ip` · `is_ip_in_range` ·
`is_ip_in_subnet_` · `is_mac` · `is_md5` · `is_sha1` · `is_sha256` · `is_sha512` · `is_url` ·
`is_windows_path` · `isfloat` · `valid_ip` · `valid_net` · `address_in_network` · `ip_to_int_` ·
`safe_int` · `validate_value_presense` · `type_correct_` · `is_python_3_9`

Use these instead of hand-rolled regexes — `is_ip_in_range` and `address_in_network` in
particular save a lot of buggy subnet code.

## URL and string helpers

`get_URLs` · `get_host_from_url` · `get_file_name_from_url` · `get_valid_file_name` ·
`quote_plus` · `unquote` · `encode_proxy_var` · `get_start_end_from_range_str` ·
`bytes_to_human_readable_size_str` · `get_random_chars` · `get_values_in_events` ·
`attacker_ips` · `victim_ips` · `get_attacked_ips`

## Rendering and output

`render_template` · `Template` · `html_string_to_pdf` · `html_file_to_pdf`

## Apps, assets, users

`get_apps` · `get_assets` · `get_asset_names` · `get_effective_user`

## Logging

`debug` · `error` · `trace_` · `print_errors` · `parse_errors` · `parse_results` ·
`parse_success` · `debug_private_error_` · `debug_private_message_` · `_dump_shell_returns`

## Unicode helpers

`convert_to_unicode` · `decode_unicode` · `decode_unicode_dict` · `decode_unicode_list` ·
`decode_unicode_parameters` · `decode_unicode_tuple` · `encode_unicode` ·
`encode_unicode_dict` · `encode_unicode_list` · `encode_unicode_parameters` ·
`encode_unicode_tuple`

## Parameter validation (custom function / connector helpers)

`_check_at_least_one_param` · `_check_one_and_only_one_param` · `_check_param_in_choices` ·
`_check_required_params` · `_get_arity` · `deduplicate_params` · `remove_none_values`

## External commands

`run_ext_command` · `run_ext_command_list`

## Not `phantom` APIs — imported symbols visible via `dir()`

These are modules/classes the platform imported into the namespace. **They are usable
without importing them**, which is why they show up in the dump:

`datetime` · `timedelta` · `ZoneInfo` · `deepcopy` · `wraps` · `xrange` · `Template` ·
`Context` · `JsonTranslator` · `LoopState`

⚠️ **`ZoneInfo` is available.** Use it for the UTC↔local conversions the SLA/audit playbooks
need, instead of hardcoding a `timedelta(hours=4)` offset that breaks on DST or a server
timezone change.

## Internal plumbing (avoid unless you know why)

`cleanse_filtered_action_results_` · `does_condition_use_ar_data_` ·
`does_condition_use_filtered_ar_data_` · `get_filter_artifact_ids_` ·
`txfrm_collected_ar_data_` · `reset_python_path_` · `set_python_path_` ·
`set_git_repo_path_`
