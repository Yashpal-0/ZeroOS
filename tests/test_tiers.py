import pytest

from zeroos.policy.tiers import MCP_PREFIX, PATH_ARGUMENTS, TIERS, Tier, tier_of

EXPECTED_AUTO = {
    "list_apps",
    "open_app",
    "open_path",
    "open_url",
    "search_files",
    "read_text_file",
    "list_folder",
    "read_clipboard",
    "notify",
    "set_volume",
}
EXPECTED_CONFIRM = {
    "write_clipboard",
    "create_folder",
    "write_text_file",
    "copy_file",
    "move_file",
    "trash_file",
    "remember",
    "forget",
    "run_command",
}


def test_there_are_exactly_nineteen_tools():
    assert len(TIERS) == 19


def test_auto_tier_matches_the_spec():
    assert {n for n, t in TIERS.items() if t is Tier.AUTO} == EXPECTED_AUTO


def test_confirm_tier_matches_the_spec():
    assert {n for n, t in TIERS.items() if t is Tier.CONFIRM} == EXPECTED_CONFIRM


def test_unknown_tool_fails_closed():
    with pytest.raises(KeyError):
        tier_of("run_shell_command")


def test_every_sandboxed_tool_is_a_known_tool():
    assert set(PATH_ARGUMENTS) <= set(TIERS)


def test_sandboxed_arguments_match_the_spec():
    assert PATH_ARGUMENTS == {
        "open_path": ("path",),
        "search_files": ("location",),
        "read_text_file": ("path",),
        "list_folder": ("path",),
        "create_folder": ("path",),
        "write_text_file": ("path",),
        "copy_file": ("source", "destination"),
        "move_file": ("source", "destination"),
        "trash_file": ("path",),
    }


def test_run_command_is_confirm_tier():
    assert tier_of("run_command") is Tier.CONFIRM


def test_run_command_has_no_sandboxed_path_argument():
    """Spec section 8: it cannot have one. A command line has no path argument
    to resolve, and a shell can construct one at runtime from anything."""
    assert "run_command" not in PATH_ARGUMENTS


def test_any_mcp_name_is_confirm():
    assert tier_of("mcp__filesystem__read_file") is Tier.CONFIRM
    assert tier_of("mcp__anything__at__all") is Tier.CONFIRM


def test_the_prefix_branch_does_not_touch_TIERS():
    """Spec section 7: no mount-time write to module state, so
    test_registry.py's three-place rule keeps meaning what it means."""
    before = dict(TIERS)
    tier_of("mcp__filesystem__read_file")
    assert TIERS == before


def test_an_unknown_non_mcp_name_still_raises():
    with pytest.raises(KeyError):
        tier_of("definitely_not_a_tool")


def test_a_non_string_name_fails_closed_with_key_error():
    with pytest.raises(KeyError):
        tier_of(5)


def test_a_name_that_only_resembles_the_prefix_still_raises():
    with pytest.raises(KeyError):
        tier_of("mcp_filesystem_read")


def test_the_prefix_is_two_underscores():
    assert MCP_PREFIX == "mcp__"
