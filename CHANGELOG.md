# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
