# Visual-editor blocks and the clipboard format

The playbook editor's copy/paste clipboard is `base64(json)` of a `coa_data`
envelope holding one or more nodes. Pasting a payload onto the canvas recreates
the blocks with every setting already filled in, which makes it a practical way
to hand a fully-configured block to someone working in the UI.

```json
{"coa_data": {
  "nodes": {"<id>": { ...node... }},
  "edges": [],
  "platform_version": "7.1.0.225",
  "coa_schema_version": "5.0.23",
  "playbook_type": "automation"
}}
```

## Node types

| Type | Purpose | Built by |
|---|---|---|
| `code` | Custom python | `soar_build_code_block` |
| `action` | Run an app action against an asset | `soar_build_action_block` |
| `decision` | Branch on comparisons | `soar_build_decision_block` |
| `format` | Build a string from datapaths | `soar_build_format_block` |
| `utility` | Call a custom function | `soar_build_custom_function_block` |
| `playbook` | Call a child playbook | `soar_build_playbook_block` |

## Things the editor is fussy about

- **`userCode` sits at node level**, not inside `data`. A code block whose code
  is nested inside `data` pastes as an empty block.
- **Action, utility and playbook nodes need a `loop` stanza** even when looping
  is off. Without it the editor flags the node as invalid. Format and decision
  nodes have none.
- **Decision nodes need an explicit `else` condition.** The builders add one.
- **`functionName` is derived from the display name**: lowercased, spaces
  replaced with underscores. It becomes the `def` name in the generated python,
  so it is also the prefix of every datapath reading the block.
- **Condition and comparison keys only need to be unique.** The UI mints UUIDs;
  the builders suffix with the node id so two pasted decision blocks cannot
  collide.

## Working out an unfamiliar node shape

Copy a working block of that type out of the editor and run
`soar_decode_vpe_block` on it. The editor is the authority on the shape — the
published documentation does not describe this format at all.
