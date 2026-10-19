"""Seed data for 13_architecture.robot (NERD036, hmd-cli-neuronsphere).

Registers two repo classes and a rendering template through the deployment
service, every name carrying the run id, so the suite runs against a control
plane whose data persists and asserts only on what it creates. Nothing is
cleared.
"""

import io
import json
import os
import time
import urllib.request
import zipfile

DEPLOYMENT_API = os.environ.get(
    "DEPLOYMENT_API_URL", "http://localhost:8080/hmd_ms_deployment"
).rstrip("/")

RUN_ID = os.environ.get("ROBOT_RUN_ID") or time.strftime("%m%d%H%M%S")
PRODUCER = f"gui-arch-bucket-{RUN_ID}"
CONSUMER = f"gui-arch-lib-{RUN_ID}"
TEMPLATE = f"gui-arch-template-{RUN_ID}"
VIEW = f"gui-arch-view-{RUN_ID}"

_PUML = (
    "@startuml\n"
    "{% for n in nodes %}rectangle \"{{ n.label }}\"\n{% endfor %}"
    "' audience: {{ vars.audience }}\n"
    "@enduml\n"
)


def _aws(name):
    return {
        "resource_namespace": "aws.neuronsphere.io",
        "resource_definition_name": name,
        "version": "0.1.0",
        "produces": True,
    }


class ArchitectureSeed:
    ROBOT_LIBRARY_SCOPE = "SUITE"

    def _op(self, op, data):
        req = urllib.request.Request(
            f"{DEPLOYMENT_API}/apiop/{op}",
            data=json.dumps(data).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            if "already has version" in e.read().decode():
                return {}
            raise

    def seed_architecture_data(self):
        """Register the classes and the template; return the names."""
        self._op("seed_base_resource_definitions", {})
        self._op(
            "add_repo_class_version",
            {
                "repo_class_name": PRODUCER,
                "version": "0.1.0",
                "dependencies": {},
                "default_configuration": {},
                "resources": {"bucket": _aws("s3-bucket")},
            },
        )
        self._op(
            "add_repo_class_version",
            {
                "repo_class_name": CONSUMER,
                "version": "0.1.0",
                "dependencies": {
                    "lib-repo": {"repo_class_name": PRODUCER, "required": "true"}
                },
                "default_configuration": {},
                "resources": {
                    "api": {**_aws("api-gateway-rest-api"), "metadata": {"connects_to": ["function"]}},
                    "function": {**_aws("lambda-function"), "metadata": {"connects_to": ["dep:lib-repo"]}},
                },
            },
        )
        self._op(
            "register_rendering_template",
            {
                "template_name": TEMPLATE,
                "version": "0.1.0",
                "title": "GUI test template",
                "descriptor": {
                    "requires_schema": "architecture.neuronsphere.io/v1",
                    "outputs": [{"path": "architecture.puml", "primary": True}],
                    "parameters": {
                        "type": "object",
                        "properties": {"audience": {"type": "string", "default": "customer"}},
                    },
                },
                "files": {"architecture.puml.j2": _PUML},
            },
        )
        return {"producer": PRODUCER, "consumer": CONSUMER, "template": TEMPLATE, "view": VIEW}

    def zip_should_contain(self, path, member, text):
        """Fail unless the zip at ``path`` has ``member`` containing ``text``."""
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if member not in names:
                raise AssertionError(f"{member} not in {names}")
            content = z.read(member).decode()
        if text not in content:
            raise AssertionError(f"{member} lacks {text!r}:\n{content}")
