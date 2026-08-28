import pytest

from splunk_soar_mcp.vpe import blocks as B


def test_emit_decode_round_trip():
    node = B.code("9", "Hello World", user_code='    phantom.debug("hi")\n')
    payload = B.emit(node)
    coa = B.decode(payload)["coa_data"]

    assert coa["platform_version"] == B.PLATFORM_VERSION
    assert list(coa["nodes"]) == ["9"]
    assert coa["nodes"]["9"]["data"]["functionName"] == "hello_world"


def test_function_name_derivation():
    assert B.function_name_for("Build Digest") == "build_digest"
    assert B.function_name_for("  Mixed Case  ") == "mixed_case"


def test_user_code_lives_at_node_level_not_in_data():
    node = B.code("9", "x", user_code="    pass\n")
    assert "userCode" in node
    assert "userCode" not in node["data"]


def test_user_code_is_compiled_and_syntax_errors_surface():
    with pytest.raises(SyntaxError):
        B.code("9", "bad", user_code="    if True\n")


def test_user_code_is_normalised_with_leading_and_trailing_newlines():
    node = B.code("9", "x", user_code="    pass")
    assert node["userCode"].startswith("\n")
    assert node["userCode"].endswith("\n")


def test_declared_outputs_are_preserved():
    node = B.code("9", "x", user_code="    pass\n", outputs=["message", "count"])
    assert node["data"]["outputVariables"] == ["message", "count"]


def test_decision_always_gets_an_else_branch():
    node = B.decision("2", "Check", "check", [{"op": ">", "param": "container:id", "value": "0"}])
    conditions = node["data"]["conditions"]
    assert [c["type"] for c in conditions] == ["if", "else"]


def test_decision_keys_are_namespaced_by_node_id():
    first = B.decision("2", "A", "a", [{"op": "==", "param": "x", "value": "1"}])
    second = B.decision("3", "B", "b", [{"op": "==", "param": "x", "value": "1"}])
    assert (
        first["data"]["conditions"][1]["conditionKey"]
        != second["data"]["conditions"][1]["conditionKey"]
    )


def test_decision_logic_is_carried_through():
    node = B.decision("2", "A", "a", [{"op": "==", "param": "x", "value": "1"}], logic="or")
    assert node["data"]["conditions"][0]["logic"] == "or"


@pytest.mark.parametrize("builder", ["action", "custom_function", "playbook"])
def test_looping_node_types_carry_a_loop_stanza(builder):
    made = {
        "action": lambda: B.action("1", "A", "block ip", "App", "7", "a", ["asset"], {}),
        "custom_function": lambda: B.custom_function("4", "C", "c", "cf", "repo", [], {}),
        "playbook": lambda: B.playbook("5", "Child", "child", "1", "local", {}),
    }[builder]()
    assert made["data"]["loop"] == B.LOOP_OFF


def test_format_node_has_no_loop_stanza():
    node = B.format_block("3", "Msg", "msg", "hello {0}", ["container:name"])
    assert "loop" not in node["data"]


def test_custom_function_fields_are_expanded_to_full_shape():
    node = B.custom_function(
        "4", "CF", "cf_block", "my_cf", "local",
        fields=[{"name": "message", "description": "the text"}],
        values={"message": "container:name"},
    )
    field = node["data"]["utilities"]["my_cf"]["fields"][0]
    assert field["name"] == "message"
    assert field["renderType"] == "datapath"
    assert field["required"] is False
    assert node["data"]["values"]["my_cf"] == {"message": "container:name"}


def test_playbook_inputs_become_datapath_lists():
    node = B.playbook("5", "Child", "child", "1", "local", {"container_id": ["container:id"]})
    assert node["data"]["inputs"]["container_id"] == {
        "datapaths": ["container:id"],
        "deduplicate": False,
    }


def test_summarize_reports_node_types():
    payload = B.emit(
        B.code("9", "Code", user_code="    pass\n"),
        B.format_block("3", "Fmt", "fmt", "{0}", ["container:name"]),
    )
    summary = B.summarize(payload)
    assert "nodes            : 2" in summary
    assert "code" in summary and "format" in summary
