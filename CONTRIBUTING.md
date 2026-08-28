# Contributing

Bug reports, endpoint corrections and new tools are all welcome.

## Getting set up

```bash
git clone https://github.com/OWNER/splunk-soar-mcp
cd splunk-soar-mcp
pip install -e ".[dev]"
pytest        # the REST layer is mocked; no SOAR instance required
ruff check .
```

## Adding a tool

1. Put it in the `tools/` module that matches its subject.
2. Give it a `@mcp.tool` decorator with a `description` that says what the tool is *for*,
   and a docstring whose `Args:` section documents every parameter — both end up in the
   schema the model reads.
3. Set `ToolAnnotations` honestly: `read_only_hint` for queries, `destructive_hint` for
   anything irreversible.
4. Register it in `server.py` under the **lowest** mode that should have it. A tool that
   writes belongs in `register_writes`; one that deletes or executes belongs in
   `register_destructive` or `run.py`.
5. Raise `SoarError` (or a subclass) for failures the caller could act on. It subclasses
   the SDK's `ToolError`, so the message reaches the model — a plain exception is masked
   as "Error executing tool".
6. Add a test. `tests/conftest.py` has the fixtures; `respx` mocks the REST layer.

## Endpoint corrections

SOAR's REST surface varies between versions, and some of it is undocumented. If a tool
targets the wrong endpoint on your version, please open an issue with your SOAR version
and the response you get — that is more useful than a guess at the right path.

## Style

`ruff` enforces the rest. Keep tool descriptions concrete: what it returns and when to
reach for it beats a restatement of the name.
