"""Bounded Tk driver admission; actual source-Xvfb evidence is separate."""

import pytest

from tools import installed_native_tk as tool


def request():
    return {"phase": "create", "window_ids": ["0x123"], "pid": 123}


@pytest.mark.parametrize(
    "field,value",
    [
        ("phase", "infer"),
        ("phase", True),
        ("pid", True),
        ("pid", 0),
        ("window_ids", []),
        ("window_ids", [True]),
        ("window_ids", ["0x123; exec unsafe"]),
        ("window_ids", ["0x1"] * 5),
    ],
)
def test_driver_refuses_unknown_or_ambiguous_target_before_loading_tk(field, value):
    row = request()
    row[field] = value
    with pytest.raises(ValueError):
        tool.admit_request(row)


def test_driver_rejects_extra_request_fields_not_arbitrary_script():
    row = request()
    row["script"] = "never execute"
    with pytest.raises(ValueError):
        tool.admit_request(row)
    assert tool.admit_request(request()) == request()


def test_tcl_arguments_remain_one_literal_list_not_eval():
    calls = []

    class FakeTk:
        def call(self, *args):
            calls.append(args)
            return args[1:] if args[0] == "list" else "done"

    driver = object.__new__(tool.Driver)
    driver.tk = FakeTk()
    driver.peer = "owned"
    literal = "{braces}; [exec never] — é 🐝"
    assert driver.send(".text", "insert", "1.0", literal) == "done"
    assert calls == [
        ("list", ".text", "insert", "1.0", literal),
        ("send", "--", "owned", (".text", "insert", "1.0", literal)),
    ]


def test_unknown_phase_refuses_before_any_remote_control():
    driver = object.__new__(tool.Driver)
    driver.send = lambda *_: pytest.fail("No remote Tk command before phase admission")
    with pytest.raises(ValueError):
        driver.run("unknown")


def test_repeated_or_unbounded_widget_tree_refuses():
    driver = object.__new__(tool.Driver)
    driver.children = lambda _: ["."]
    with pytest.raises(ValueError, match="repeated"):
        driver.widgets()


def test_ambiguous_label_is_not_silently_first_control():
    driver = object.__new__(tool.Driver)
    with pytest.raises(ValueError, match="ambiguous"):
        driver.unique(["a", "b"], lambda _: True, "save")


def controlled_environment(tmp_path, monkeypatch):
    from pathlib import Path

    auth = tmp_path / "xauthority"
    auth.write_bytes(b"fictional never used authorization")
    auth.chmod(0o600)
    req = tmp_path / "request.json"
    req.write_text("{}")
    monkeypatch.setenv("DISPLAY", ":97")
    monkeypatch.setenv("XAUTHORITY", str(auth))
    old = Path.is_file
    monkeypatch.setattr(
        Path, "is_file", lambda p: True if str(p) == "/.dockerenv" else old(p)
    )
    old_iter = Path.iterdir
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda p: iter([Path("lo")]) if str(p) == "/sys/class/net" else old_iter(p),
    )
    return auth, req


def test_owned_container_environment_is_admitted_without_loading_tk(
    tmp_path, monkeypatch
):
    _, req = controlled_environment(tmp_path, monkeypatch)
    assert tool.admit_environment(req) is None


@pytest.mark.parametrize(
    "attack",
    ["public_display", "foreign_auth", "auth_symlink", "auth_public", "request_large"],
)
def test_driver_refuses_display_or_file_ownership_gaps_before_tk(
    tmp_path, monkeypatch, attack
):
    auth, req = controlled_environment(tmp_path, monkeypatch)
    if attack == "public_display":
        monkeypatch.setenv("DISPLAY", "localhost:0")
    elif attack == "foreign_auth":
        monkeypatch.setenv("XAUTHORITY", str(tmp_path.parent / "external"))
    elif attack == "auth_symlink":
        copy = tmp_path / "other"
        copy.write_bytes(auth.read_bytes())
        copy.chmod(0o600)
        auth.unlink()
        auth.symlink_to(copy)
    elif attack == "auth_public":
        auth.chmod(0o644)
    else:
        req.write_bytes(b" " * 8193)
    with pytest.raises(ValueError):
        tool.admit_environment(req)


def test_main_refuses_host_before_tk_or_target_action(tmp_path, monkeypatch):
    import json
    import sys
    from pathlib import Path

    req = tmp_path / "request.json"
    req.write_text(json.dumps(request()), encoding="utf-8")
    old = Path.is_file
    monkeypatch.setattr(
        Path, "is_file", lambda p: False if str(p) == "/.dockerenv" else old(p)
    )
    monkeypatch.setitem(
        sys.modules,
        "tkinter",
        type(
            "ForbiddenTk",
            (),
            {"Tk": lambda: pytest.fail("No root or customer display on host")},
        ),
    )
    with pytest.raises(ValueError, match="owning"):
        tool.main(["--request", str(req)])
