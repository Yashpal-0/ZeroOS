import pytest

from zeroos.policy import sandbox


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Downloads").mkdir()
    (tmp_path / ".ssh").mkdir()
    return tmp_path


def test_allows_a_path_inside_home(home):
    assert sandbox.resolve(str(home / "Documents" / "a.txt")) == home / "Documents" / "a.txt"


def test_allows_home_itself(home):
    assert sandbox.resolve(str(home)) == home


def test_allows_a_file_that_does_not_exist_yet(home):
    # write_text_file needs this: the parent exists, the file does not.
    assert sandbox.resolve(str(home / "Documents" / "new.txt")) == home / "Documents" / "new.txt"


def test_expands_tilde(home):
    assert sandbox.resolve("~/Documents") == home / "Documents"


def test_treats_relative_paths_as_relative_to_home(home):
    assert sandbox.resolve("Documents") == home / "Documents"


def test_treats_multi_segment_relative_paths_as_relative_to_home(home):
    # The model emits these unprompted: asked to file a download, it returned
    # {"destination": "Documents/Taxes/report.pdf"} with no leading slash.
    assert sandbox.resolve("Documents/Taxes/report.pdf") == home / "Documents" / "Taxes" / "report.pdf"


def test_refuses_a_path_outside_home(home):
    with pytest.raises(sandbox.Refused):
        sandbox.resolve("/etc/passwd")


def test_refuses_dotdot_traversal_out_of_home(home):
    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(home / "Documents" / ".." / ".." / ".." / "etc" / "passwd"))


def test_refuses_the_ssh_directory(home):
    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(home / ".ssh" / "id_rsa"))


def test_refuses_the_ssh_directory_itself(home):
    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(home / ".ssh"))


def test_refuses_the_zeroos_log_directory(home):
    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(home / ".local" / "share" / "ZeroOS" / "actions.log"))


def test_refuses_a_symlink_pointing_into_a_denied_directory(home):
    link = home / "Documents" / "keys"
    link.symlink_to(home / ".ssh")
    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(link / "id_rsa"))


def test_refuses_a_symlink_pointing_outside_home(home):
    link = home / "Documents" / "escape"
    link.symlink_to("/etc")
    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(link / "passwd"))


def test_refusal_carries_the_user_facing_message(home):
    with pytest.raises(sandbox.Refused) as caught:
        sandbox.resolve("/etc/passwd")
    assert caught.value.message == sandbox.REFUSAL_MESSAGE
