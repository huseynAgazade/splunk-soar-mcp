from splunk_soar_mcp.tools.playbooks import split_blocks

SOURCE = '''\
import phantom.rules as phantom
import json


def on_start(container):
    phantom.debug("start")
    format_1(container=container)
    return


@phantom.playbook_block()
def format_1(action=None, success=None, container=None, **kwargs):
    phantom.format(container=container, template="hi {0}")
    return


@phantom.playbook_block()
def on_finish(container, summary):
    return
'''


def test_splits_every_top_level_def():
    assert list(split_blocks(SOURCE)) == ["on_start", "format_1", "on_finish"]


def test_decorator_is_kept_with_its_block():
    assert split_blocks(SOURCE)["format_1"].startswith("@phantom.playbook_block()")


def test_undecorated_block_is_still_found():
    assert split_blocks(SOURCE)["on_start"].startswith("def on_start(")


def test_block_body_stops_at_the_next_def():
    assert "def on_finish" not in split_blocks(SOURCE)["format_1"]


def test_source_without_defs_yields_nothing():
    assert split_blocks("x = 1\n") == {}
