"""Chart tests for how the db-credentials role becomes the DB secret and DB_NAME.

Renders the real chart with ``helm template``. The relpub incident (2026-10-13):
db-credentials asked for a bare ``postgres`` Resource, nsctl auto-bound it to the
environment's shared ``environment-db`` (admin secret, no ``database_name``), and
the chart rendered an ExternalSecret on the admin secret and an empty DB_NAME --
pods that never started and no error anywhere. These tests pin the chart to
reading the db-credentials role only, and to failing the render on that shape.
"""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
CHART = REPO / "src" / "helm"
CONFIG_LOCAL = REPO / "meta-data" / "config_local.json"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not on PATH")

ACCOUNT_SECRET = "hmd_db_hmd-postgres-base_aaa_local_reg1_none_deployment_gui"
ADMIN_SECRET = "environment-db_hmd-postgres-rds_relpub_db-secret"


def _resource(name, definition, output, tags=None):
    return {
        "resource_name": name,
        "resource_definition": {
            "resource_namespace": "database.neuronsphere.io",
            "resource_definition_name": definition,
            "version": "0.1.0",
        },
        "output": output,
        "tags": tags or [],
    }


def _account():
    return _resource(
        "deployment_gui",
        "database-account",
        {"database_name": "deployment_gui", "secret_name": ACCOUNT_SECRET},
    )


def _admin_postgres():
    """What environment-db (hmd-postgres-rds, local overlay) emits."""
    return _resource(
        "environment-db",
        "postgres",
        {
            "host": "hmd_db",
            "port": 5432,
            "secret_name": ADMIN_SECRET,
            "engine_version": "15",
        },
    )


def _values(db_resources):
    values = json.loads(CONFIG_LOCAL.read_text())
    values = copy.deepcopy(values)
    values["dependencies"]["db-credentials"] = {"hmd_resources": db_resources}
    return values


def _render(values, tmp_path, template):
    values_file = tmp_path / "values.json"
    values_file.write_text(json.dumps(values))
    return subprocess.run(
        [
            "helm",
            "template",
            "gui",
            str(CHART),
            "-f",
            str(values_file),
            "--show-only",
            f"templates/{template}",
        ],
        capture_output=True,
        text=True,
    )


def _doc(result):
    assert result.returncode == 0, result.stderr
    return yaml.safe_load(result.stdout)


def _remote_keys(external_secret):
    return {d["remoteRef"]["key"] for d in external_secret["spec"]["data"]}


def test_database_account_resource_drives_secret_and_db_name(tmp_path):
    values = _values([_account()])

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))
    cm = _doc(_render(values, tmp_path, "configmap.yaml"))

    assert _remote_keys(es) == {ACCOUNT_SECRET}
    assert cm["data"]["DB_NAME"] == "deployment_gui"


def test_postgres_on_another_role_is_ignored(tmp_path):
    """The lookup is scoped to db-credentials; a postgres elsewhere can't leak in."""
    values = _values([_account()])
    values["dependencies"]["compute"]["hmd_resources"].append(_admin_postgres())

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _remote_keys(es) == {ACCOUNT_SECRET}


def test_shared_admin_postgres_bound_to_db_credentials_fails_render(tmp_path):
    """The relpub shape: fail the render, naming the role and what was bound."""
    values = _values([_admin_postgres()])

    result = _render(values, tmp_path, "hmd-db-external-secret.yaml")

    assert result.returncode != 0
    assert "db-credentials" in result.stderr
    assert "environment-db" in result.stderr
    assert "database_name" in result.stderr


def test_per_database_postgres_still_accepted(tmp_path):
    """The legacy local dev_db.py producer emits per-database postgres Resources."""
    values = json.loads(CONFIG_LOCAL.read_text())
    legacy = _resource(
        "local-db-deployment_gui",
        "postgres",
        {"database_name": "deployment_gui", "secret_name": ACCOUNT_SECRET},
    )
    values["dependencies"]["db-credentials"] = {"hmd_resources": [legacy]}

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _remote_keys(es) == {ACCOUNT_SECRET}


def test_cloud_dependency_chain_unchanged(tmp_path):
    values = json.loads(CONFIG_LOCAL.read_text())
    values["env"].update(
        HMD_ENVIRONMENT="dev", HMD_REGION="reg1", HMD_CUSTOMER_CODE="acme"
    )
    values["dependencies"]["db-credentials"] = {
        "instance_name": "gui-db",
        "dependencies": {
            "database-instance": {
                "instance_name": "pg",
                "repo_name": "hmd-postgres-rds",
                "deployment_id": "aaa",
            }
        },
    }
    values["details"] = {"gui-db": {"db_name": "deployment_gui"}}

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))
    cm = _doc(_render(values, tmp_path, "configmap.yaml"))

    assert _remote_keys(es) == {"pg_hmd-postgres-rds_aaa_dev_reg1_acme_deployment_gui"}
    assert (
        es["metadata"]["name"] == "pg-hmd-postgres-rds-aaa-dev-reg1-acme-deployment-gui"
    )
    assert cm["data"]["DB_NAME"] == "deployment_gui"


def test_no_resource_and_no_chain_fails_render(tmp_path):
    values = _values([])

    result = _render(values, tmp_path, "hmd-db-external-secret.yaml")

    assert result.returncode != 0
    assert "db-credentials" in result.stderr


def test_config_local_renders(tmp_path):
    values = json.loads(CONFIG_LOCAL.read_text())

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _remote_keys(es) == {ACCOUNT_SECRET}


# --- Which ClusterSecretStore the DB secret is read through ------------------
# hmd-ms-dbaccount writes account secrets with hmd_lib_secrets_backend, which
# stores them in SSM Parameter Store (and migrates older Secrets Manager copies
# there). relpub, 2026-10-14: the ExternalSecret read the account through the
# Secrets Manager store -> "Secret does not exist" although the account existed.


def _store(external_secret):
    return external_secret["spec"]["secretStoreRef"]["name"]


def test_database_account_secret_read_through_parameter_store(tmp_path):
    values = _values([_account()])

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _store(es) == "aws-parameter-store"


def test_parameter_store_name_from_values(tmp_path):
    values = _values([_account()])
    values["parameterStoreSecretStore"] = {"name": "custom-ps"}

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _store(es) == "custom-ps"


def test_parameter_store_name_from_ext_secrets_details(tmp_path):
    values = _values([_account()])
    values["dependencies"]["ext-secrets"] = {"instance_name": "ext-secrets"}
    values["details"] = {
        "ext-secrets": {
            "clusterSecretStore": {"name": "sm"},
            "parameterStoreSecretStore": {"name": "ps-from-details"},
        }
    }
    del values["clusterSecretStore"]

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _store(es) == "ps-from-details"


def test_legacy_per_database_postgres_keeps_secrets_manager(tmp_path):
    """dev_db.py writes its per-database secrets to Secrets Manager."""
    values = _values(
        [
            _resource(
                "local-db-deployment_gui",
                "postgres",
                {"database_name": "deployment_gui", "secret_name": ACCOUNT_SECRET},
            )
        ]
    )

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _store(es) == "aws-secrets-manager"


def _cloud_chain_values():
    values = json.loads(CONFIG_LOCAL.read_text())
    values["dependencies"]["db-credentials"] = {
        "instance_name": "gui-db",
        "dependencies": {
            "database-instance": {
                "instance_name": "pg",
                "repo_name": "hmd-postgres-rds",
                "deployment_id": "aaa",
            }
        },
    }
    values["details"] = {"gui-db": {"db_name": "deployment_gui"}}
    return values


def test_cloud_chain_keeps_cluster_secret_store_by_default(tmp_path):
    es = _doc(_render(_cloud_chain_values(), tmp_path, "hmd-db-external-secret.yaml"))

    assert _store(es) == "aws-secrets-manager"


def test_cloud_chain_platform_secret_store_knob(tmp_path):
    values = _cloud_chain_values()
    values["platformSecretStore"] = "parameterStoreSecretStore"

    es = _doc(_render(values, tmp_path, "hmd-db-external-secret.yaml"))

    assert _store(es) == "aws-parameter-store"
