# Datapaths — how one playbook block reads another's output

A datapath is the string a block uses to pull a value out of the run. Getting
the *form* right matters more than the field name: the wrong form fails at run
time, usually with a `JSONDecodeError` out of `get_block_result`, and the
message does not say which block was at fault.

## The forms, by producing block type

| Producer | Datapath to read it | Notes |
|---|---|---|
| Container | `container:id`, `container:name`, `container:label`, `container:status` | Always available. |
| Artifact | `artifact:*.cef.sourceAddress`, `artifact:*.id` | The `*` fans out — one downstream run per artifact. |
| App action | `<block>:action_result.data.*.<field>` | Also `.summary.<field>`, `.parameter.<field>`, `.status`, `.message`. |
| Code block | `<block>:custom_function:<output>` | The output must be declared on the block. |
| Custom function block | `<block>:custom_function_result.data.<output>` | **Not** the `custom_function:` form — that is the code-block shape and fails at run time. |
| Format block | `<block>:formatted_data` | `formatted_data.*` instead fans out one run per row, which breaks consumers expecting a single value. |
| Child playbook | `<block>:playbook_<name>:output.<name>` | Only when the child block is synchronous. |
| Playbook input | `playbook_input:<name>` | For input playbooks. |

## Fan-out

A `*` anywhere in a datapath multiplies the downstream block: `artifact:*.cef.ip`
on a container with twelve artifacts runs the consumer twelve times. That is
usually what you want for per-observable work and never what you want for a
single summary message.

## Declaring outputs

A code block's output is only saved if it is declared on the block **and**
assigned in the code as `<function_name>__<output_name>`:

```python
    build_digest__message = "..."      # block function_name is build_digest,
                                       # declared output is message
```

An undeclared output is silently dropped, and the block reading it fails.

## Collecting inside code

Relying on the variable names the editor generates is fragile — they change when
the block is renamed or re-wired. Inside a code block, collect explicitly:

```python
    rows = phantom.collect2(
        container=container,
        datapath=["artifact:*.cef.sourceAddress", "artifact:*.id"],
    )
    for value, artifact_id in rows:
        ...
```

`collect2` returns a list of tuples, one per requested datapath, in order.
