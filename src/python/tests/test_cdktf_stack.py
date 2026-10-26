"""The CDKTF stack creates the GUI's own Okta service app.

The GUI calls hmd-ms-deployment as a service account whenever it has no user
token to forward (MCP gateway discovery, MCP API-key callers). A cloud GUI with
Okta always needs one, so the stack creates it, and its secret
(``okta-<instance>-<repo>-<did>``) is what the chart syncs into the pod.

The stack's imports pull in cdktf and jsii, which need a node runtime, so they
are stubbed here: the test is about what the stack asks the factories for.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

import pytest

STACK = Path(__file__).resolve().parents[2] / "cdktf" / "cdktf_local.py"


class _BaseStack:
    def __init__(
        self,
        scope,
        ns,
        instance_name,
        repo_name,
        deployment_id,
        environment,
        region,
        customer_code,
        repo_version,
        account,
        profile,
        config,
    ):
        self.instance_name = instance_name
        self.environment = environment
        self.hmd_region = region
        self.profile = profile
        self.account = account
        self.config = config
        self.is_local = environment == "local"


def _module(name, **attrs):
    module = ModuleType(name)
    module.__dict__.update(attrs)
    return module


@pytest.fixture
def okta():
    okta_factory = mock.Mock(name="Okta")
    stubs = {
        "cdktf": _module("cdktf", Fn=mock.Mock()),
        "constructs": _module("constructs", Construct=object),
        "hmd_cli_tools": _module("hmd_cli_tools"),
        "hmd_cli_tools.hmd_cli_tools": _module(
            "hmd_cli_tools.hmd_cli_tools",
            get_deployer_target_session=mock.Mock(),
            get_secret=mock.Mock(return_value={"secret-key": "k"}),
        ),
        "hmd_lib_cdktf": _module("hmd_lib_cdktf"),
        "hmd_lib_cdktf.hmd_lib_cdktf": _module(
            "hmd_lib_cdktf.hmd_lib_cdktf", HmdCdkTfStack=_BaseStack
        ),
        "hmd_lib_cdktf_factories": _module(
            "hmd_lib_cdktf_factories", Okta=okta_factory, SecretsManager=mock.Mock()
        ),
    }
    with mock.patch.dict(sys.modules, stubs):
        yield okta_factory


def _synth(environment, config):
    spec = importlib.util.spec_from_file_location("gui_cdktf_stack", STACK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CdkTfStack(
        None,
        "ns",
        "gui",
        "hmd-app-neuronsphere-core",
        "aaa",
        environment,
        "reg1",
        "hmd",
        "0.1.11",
        "123",
        "profile",
        config,
    )


def test_cloud_with_okta_creates_the_service_app_and_its_secret(okta):
    _synth("admin", {"config": {"oktaAuth": True}})
    okta.return_value.oauth_service_app.assert_called_once_with(create_secret=True)


def test_okta_off_creates_no_service_app(okta):
    _synth("admin", {"config": {"oktaAuth": False}})
    okta.return_value.oauth_service_app.assert_not_called()


def test_local_creates_no_service_app(okta):
    """Okta is real SaaS identity the local platform does not emulate."""
    _synth("local", {"config": {"oktaAuth": True}})
    okta.return_value.oauth_service_app.assert_not_called()
