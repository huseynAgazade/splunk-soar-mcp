from splunk_soar_mcp.formatting import details, listing, table


def test_table_renders_header_and_rows():
    out = table([{"id": 1, "name": "alpha"}], ["id", "name"])
    assert "id" in out and "alpha" in out
    assert "1 row(s)" in out


def test_table_reports_truncation_against_total():
    out = table([{"id": 1}], ["id"], total=90)
    assert "1 of 90 shown" in out


def test_empty_table_uses_the_empty_message():
    assert table([], ["id"], empty="nothing here") == "nothing here"


def test_none_renders_as_dash_and_bools_as_words():
    out = table([{"a": None, "b": True}], ["a", "b"])
    assert "-" in out and "yes" in out


def test_long_cells_are_truncated():
    out = table([{"a": "x" * 200}], ["a"])
    assert "…" in out
    assert "x" * 200 not in out


def test_newlines_in_cells_do_not_break_the_table():
    out = table([{"a": "one\ntwo"}], ["a"])
    assert "one two" in out
    assert "1 row(s)" in out


def test_listing_honours_as_json():
    payload = {"count": 1, "data": [{"id": 5, "name": "x"}]}
    assert '"id": 5' in listing(payload, ["id"], as_json=True)


def test_details_skips_absent_keys():
    out = details({"id": 3}, ["id", "missing"])
    assert "id" in out and "missing" not in out
