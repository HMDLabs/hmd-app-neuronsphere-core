"""`helm template` renders of the chart, with and without Okta.

The local NeuronSphere deploy has no Okta: Okta is real SaaS identity that Floci
does not emulate, so the ``okta-app`` dependency role is omitted from the local
BOM entirely and ``config.oktaAuth`` is false. Several templates reach into that
role with ``index .Values "dependencies" "okta-app" ...``, which is a *render
time* failure when the role is absent -- not a runtime one -- so a unit test that
never invokes helm cannot catch it. Hence these tests shell out to helm.

Cloud is the ``oktaAuth: true`` case and must keep emitting the ExternalSecrets
and the ``OAUTH_*`` env references exactly as before.
"""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART_DIR = REPO_ROOT / "src" / "helm"
MANIFEST = REPO_ROOT / "meta-data" / "manifest.json"
CONFIG_LOCAL = REPO_ROOT / "meta-data" / "config_local.json"

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None, reason="helm CLI not installed"
)


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _base_values() -> dict:
    """The chart's effective values for a local deploy.

    Mirrors how ms-deployment builds them: the manifest's
    ``deploy.default_configuration`` deep-updated with the instance's
    configuration. ``config_local.json`` stands in for the latter -- it already
    carries the resolved ``dependencies``/``hmd_resources``/``env`` blocks a real
    deploy would attach.
    """
    default_config = json.loads(MANIFEST.read_text())["deploy"]["default_configuration"]
    return _deep_merge(default_config, json.loads(CONFIG_LOCAL.read_text()))


def _render(overrides: dict = None, drop_roles=()) -> str:
    values = _deep_merge(_base_values(), overrides or {})
    for role in drop_roles:
        values.get("dependencies", {}).pop(role, None)
    proc = subprocess.run(
        ["helm", "template", "deployment-gui", str(CHART_DIR), "-f", "-"],
        input=yaml.safe_dump(values),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"helm template failed:\n{proc.stderr}"
    return proc.stdout


def test_okta_enabled_emits_okta_wiring():
    """Cloud path: the ExternalSecrets and OAUTH_* env refs are present."""
    out = _render({"config": {"oktaAuth": True}})
    assert "okta-web-application" in out
    assert "okta-global" in out
    assert "OAUTH_CLIENT_ID" in out
    assert "OAUTH_PROVIDER_URL" in out
    assert "OKTA_SUPERUSER_GROUPS" in out


def test_okta_disabled_without_role_renders():
    """Local path: no ``okta-app`` role at all, and nothing references Okta.

    Dropping the role is the part that breaks a naive guard -- the okta
    ExternalSecret template resolves the role in its very first lines, before any
    conditional, so the whole file has to sit inside the guard.
    """
    out = _render({"config": {"oktaAuth": False}}, drop_roles=("okta-app",))
    assert "okta-web-application" not in out
    assert "okta-global" not in out
    assert "OAUTH_CLIENT_ID" not in out
    assert "OAUTH_CLIENT_SECRET" not in out
    assert "OAUTH_PROVIDER_URL" not in out
    assert "OKTA_SUPERUSER_GROUPS" not in out
    assert "OKTA_GROUP_MAPPING" not in out


def test_okta_disabled_still_deploys_the_app():
    """Turning Okta off must not cost us the Deployment, Service or Ingress."""
    out = _render({"config": {"oktaAuth": False}}, drop_roles=("okta-app",))
    kinds = {
        doc["kind"]
        for doc in yaml.safe_load_all(out)
        if isinstance(doc, dict) and "kind" in doc
    }
    assert {"Deployment", "Service", "Ingress", "ConfigMap"} <= kinds
    # The DB and Django-secret ExternalSecrets are unrelated to Okta.
    assert "deployment-gui-django-secret" in out


def test_deployment_api_url_uses_explicit_override():
    """``config.deploymentApiUrl`` wins over the derived cloud API-Gateway URL."""
    out = _render(
        {"config": {"deploymentApiUrl": "http://hmd_proxy/hmd_ms_deployment"}}
    )
    assert "http://hmd_proxy/hmd_ms_deployment" in out


def test_deployment_api_url_falls_back_to_the_derived_cloud_url():
    """Without an override, DEPLOYMENT_API_URL is derived from the
    deployment-service dependency's instance name and the env DID/region/
    customer/environment -- the branch config_local.json's fixture always
    overrides, so it went unexercised by every other test here. That let a
    stray trailing ``-}}`` on the fallback's variable assignment through: it
    ate the next line's leading indentation and merged DEPLOYMENT_API_URL onto
    the previous ConfigMap key's line, which is invalid YAML that ``helm
    template`` rejects -- ``_render`` asserts a zero return code, so this
    regresses loudly instead of silently.
    """
    out = _render(
        {
            "config": {"deploymentApiUrl": None},
            "dependencies": {"deployment-service": {"instance_name": "ms-deployment"}},
            "env": {
                "HMD_DID": "aaa",
                "HMD_REGION": "reg1",
                "HMD_CUSTOMER_CODE": "hmdtr1",
                "HMD_ENVIRONMENT": "admin",
            },
        }
    )
    assert (
        'DEPLOYMENT_API_URL: "https://ms-deployment-aaa-reg1.hmdtr1-admin-neuronsphere.io"'
        in out
    )


def _init_args(rendered: str) -> str:
    """The migrate initContainer's shell args, or its plain command."""
    for doc in yaml.safe_load_all(rendered):
        if not isinstance(doc, dict) or doc.get("kind") != "Deployment":
            continue
        for container in doc["spec"]["template"]["spec"].get("initContainers", []):
            if container["name"] == "migrate":
                return "\n".join(container.get("args") or container["command"])
    raise AssertionError("no migrate initContainer rendered")


def test_local_mcp_key_is_minted_by_the_migrate_init_container():
    """The bootstrap bender authenticates with, mirroring createLocalSuperuser."""
    out = _render(
        {
            "config": {
                "createLocalMcpKey": True,
                "localMcpApiKey": "nsmcp_a_local_bootstrap_key",
                "localSuperuserUsername": "testadmin",
            }
        }
    )
    args = _init_args(out)
    assert "manage.py migrate --noinput" in args
    assert "create_mcp_api_key --user testadmin --name bender" in args
    # Idempotent, and never fatal to the deploy: a re-deploy must stay green.
    assert "--if-not-exists" in args
    assert args.strip().endswith("|| true")
    # The key reaches the command through env, not the argv in the pod spec.
    assert "MCP_LOCAL_API_KEY" in out
    assert "nsmcp_a_local_bootstrap_key" in out


def test_cloud_leaves_the_migrate_init_container_alone():
    """Neither local bootstrap runs when the flags are absent (the cloud case)."""
    out = _render({"config": {"createLocalSuperuser": None, "createLocalMcpKey": None}})
    args = _init_args(out)
    assert "create_mcp_api_key" not in args
    assert "createsuperuser" not in args
    assert "MCP_LOCAL_API_KEY" not in out


def test_mcp_allowed_origins_follows_the_deploy_scheme():
    """bender speaks http to the local deploy; an https origin would be rejected."""
    local = _render({"config": {"localHttp": True}})
    assert 'MCP_ALLOWED_ORIGINS: "http://' in local
    cloud = _render({"config": {"localHttp": None}})
    assert 'MCP_ALLOWED_ORIGINS: "https://' in cloud


def test_mcp_base_url_follows_the_deploy_scheme():
    """RemoteAuthProvider builds the discovery document from this origin."""
    local = _render({"config": {"localHttp": True}})
    assert 'MCP_BASE_URL: "http://' in local
    cloud = _render({"config": {"localHttp": None}})
    assert 'MCP_BASE_URL: "https://' in cloud


def test_cloud_enables_the_okta_bearer_path():
    """Cloud has no API keys, so Okta is the only credential -- and must be on.

    With both off and DEBUG false the server refuses to start (build_auth_provider),
    so this pairing is what makes the cloud configuration bootable at all.
    """
    out = _render({"config": {"oktaAuth": True, "localHttp": None}})
    assert 'MCP_OKTA_ENABLED: "true"' in out
    assert 'MCP_API_KEYS_ENABLED: "false"' in out
    assert 'MCP_OKTA_AUDIENCE: "api://neuronsphere"' in out


def test_the_local_deploy_leaves_okta_off_and_keeps_its_api_key():
    out = _render()
    assert 'MCP_OKTA_ENABLED: "false"' in out
    assert "MCP_OKTA_AUDIENCE" not in out
    assert 'MCP_API_KEYS_ENABLED: "true"' in out


def test_the_downstream_token_mode_defaults_to_passthrough():
    assert 'MCP_DOWNSTREAM_TOKEN_MODE: "passthrough"' in _render()
    assert 'MCP_DOWNSTREAM_TOKEN_MODE: "service"' in _render(
        {"config": {"mcpDownstreamTokenMode": "service"}}
    )
