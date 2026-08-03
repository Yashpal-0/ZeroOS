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


def test_refuses_ssh_under_a_symlinked_home_before_ssh_is_created(tmp_path, monkeypatch):
    # ~/.ssh does not exist yet. If a denied root that doesn't exist is
    # left unresolved while a symlinked home is resolved, the two paths'
    # prefixes no longer match and containment silently fails open.
    real_home = tmp_path / "real_home"
    real_home.mkdir()
    home_link = tmp_path / "home_link"
    home_link.symlink_to(real_home)
    monkeypatch.setenv("ZEROOS_HOME", str(home_link))

    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(home_link / ".ssh" / "authorized_keys"))


def test_refuses_the_action_log_under_a_relocated_xdg_data_home(tmp_path, monkeypatch):
    # Same shape as above, but for the XDG-relocated data dir: the ZeroOS
    # data directory doesn't exist yet, and XDG_DATA_HOME is itself a
    # symlink, so the denylist must be derived from paths.data_dir() and
    # resolved unconditionally to still catch it.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ZEROOS_HOME", str(home))

    real_data = home / "real_data"
    real_data.mkdir()
    data_link = home / "xdg_data"
    data_link.symlink_to(real_data)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_link))

    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(data_link / "ZeroOS" / "actions.log"))


def test_refuses_a_null_byte_instead_of_raising(home):
    with pytest.raises(sandbox.Refused):
        sandbox.resolve("Documents/a\0b")


def test_refuses_the_keyring_directory_under_a_relocated_xdg_data_home(tmp_path, monkeypatch):
    # keyrings was still hardcoded to .local/share/keyrings after the round-1
    # fix, so a relocated XDG_DATA_HOME left the real keyring directory
    # unprotected while the denylist guarded an empty one.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ZEROOS_HOME", str(home))

    xdg_data = home / "xdg_data"
    xdg_data.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))

    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(xdg_data / "keyrings" / "login.keyring"))


def test_refuses_config_dir_under_a_relocated_xdg_config_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ZEROOS_HOME", str(home))

    xdg_config = home / "xdg_config"
    xdg_config.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(xdg_config / "ZeroOS" / "settings.json"))


def test_the_memory_file_is_denied_under_a_relocated_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from zeroos.platform import memory

    with pytest.raises(sandbox.Refused):
        sandbox.resolve(str(memory.path()))
