import secrets

from cdktf import Fn
from constructs import Construct
from hmd_cli_tools.hmd_cli_tools import get_deployer_target_session, get_secret
from hmd_lib_cdktf.hmd_lib_cdktf import HmdCdkTfStack
from hmd_lib_cdktf_factories import Okta, SecretsManager


def get_django_secret_name(
    instance_name: str, repo_name: str, deployment_id: str
) -> str:
    return f"django-{instance_name}-{repo_name}-{deployment_id}"


class CdkTfStack(HmdCdkTfStack):
    def __init__(
        self,
        scope: Construct,
        ns: str,
        instance_name: str,
        repo_name: str,
        deployment_id: str,
        environment: str,
        region: str,
        customer_code,
        repo_version: str,
        account_number: str,
        profile: str,
        config: dict,
    ):
        super().__init__(
            scope,
            ns,
            instance_name,
            repo_name,
            deployment_id,
            environment,
            region,
            customer_code,
            repo_version,
            account_number,
            profile,
            config,
        )

        # Keeps the okta-provider-01 config in synth so Terraform can destroy
        # legacy inline okta_app_oauth / group_assignment resources still in
        # state from before the okta-app dep refactor. Safe to remove once
        # those orphans are gone.
        Okta(self)

        django_secret_name = get_django_secret_name(
            instance_name, repo_name, deployment_id
        )
        session = get_deployer_target_session(
            self.hmd_region, self.profile, self.account
        )
        try:
            existing = get_secret(session, django_secret_name)
        except Exception as e:
            print(e)
            existing = None
        if isinstance(existing, dict) and existing.get("secret-key"):
            django_secret_value = existing["secret-key"]
        else:
            django_secret_value = secrets.token_urlsafe(50)

        sm = SecretsManager(self)
        django_secret = sm.secret(
            django_secret_name, "Django SECRET_KEY for hmd-app-neuronsphere"
        )
        sm.secret_version(
            django_secret_name,
            django_secret,
            Fn.jsonencode({"secret-key": django_secret_value}),
        )
