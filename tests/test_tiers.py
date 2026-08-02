import pytest

from zeroos.policy.tiers import PATH_ARGUMENTS, TIERS, Tier, tier_of

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
}


def test_there_are_exactly_sixteen_tools():
    assert len(TIERS) == 16


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
