"""Inert boundary controls for an explicitly owned qualification browser.

No browser, Sinter process, container or provider is launched. The supplied
owner's cleanup semantics are qualified separately by its own tests and receipt.
"""

import argparse
import sys
import types
from unittest.mock import Mock, patch

import pytest

from tools import _support
from tools import installed_workflow_browser as workflow


class BodyFailure(Exception):
    pass


@pytest.mark.parametrize("owned", [False, True])
@pytest.mark.parametrize("during_launch", [False, True])
def test_workflow_launch_and_body_failure_reach_selected_session(
    tmp_path, owned, during_launch
):
    driver = object()
    browser = Mock()
    failure = BodyFailure("original fictional UI failure")
    browser.new_context.side_effect = failure
    manager = Mock()
    manager.__enter__ = Mock(return_value=driver)
    manager.__exit__ = Mock(return_value=False)
    legacy = Mock(return_value=manager)
    owner = Mock(return_value=manager)
    owner.launch.return_value = browser
    api = types.ModuleType("playwright.sync_api")
    api.expect = Mock()
    api.sync_playwright = legacy
    args = argparse.Namespace(output=tmp_path, chromium=tmp_path / "inert-chromium")
    relay = argparse.Namespace(server_address=("127.0.0.1", 1))
    with (
        patch.dict(sys.modules, {"playwright.sync_api": api}),
        patch.object(_support, "launch_chromium", return_value=browser) as launch,
        pytest.raises(BodyFailure) as caught,
    ):
        if during_launch:
            (owner.launch if owned else launch).side_effect = failure
        workflow.browser_workflow(
            args,
            tmp_path,
            relay,
            {},
            [],
            **({"browser_session": owner} if owned else {}),
        )
    assert caught.value is failure
    if during_launch:
        browser.close.assert_not_called()
    else:
        browser.close.assert_called_once_with()
    manager.__exit__.assert_called_once()
    error_type, error, traceback = manager.__exit__.call_args.args
    assert error_type is BodyFailure and error is failure
    assert traceback.tb_frame.f_code is workflow.browser_workflow.__code__
    if owned:
        owner.assert_called_once_with()
        owner.launch.assert_called_once_with(driver, args.chromium)
        legacy.assert_not_called()
        launch.assert_not_called()
    else:
        legacy.assert_called_once_with()
        launch.assert_called_once_with(driver, args.chromium)
        owner.assert_not_called()
        owner.launch.assert_not_called()
