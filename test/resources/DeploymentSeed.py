"""Robot Framework library to clear and seed deployment service data."""

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request


def _encode_mapping(value) -> str:
    """Encode a ``mapping`` attribute for the CRUD PUT endpoint: hmd_ms_base
    transmits mapping/collection/blob attributes as base64-encoded JSON."""
    return base64.b64encode(json.dumps(value).encode()).decode()


# Reachable from the bender container over neuronsphere_default. Overridable via
# DEPLOYMENT_API_URL; defaults to the local nginx proxy (hmd_proxy) that fronts the
# deployment-service Lambda (the old hmd_gateway name no longer resolves).
DEPLOYMENT_API = os.environ.get(
    "DEPLOYMENT_API_URL", "http://hmd_proxy/hmd_ms_deployment"
)

# DB connection details for the deployment service postgres
DB_CONTAINER = "hmd_db"
DB_USER = "hmd_ms_deployment"
DB_NAME = "hmd_ms_deployment"

# ---------------------------------------------------------------------------
# Seed data: 22 representative instances from a real dev BOM snapshot.
# Organized in dependency layers so every dep target exists in the set.
# Dependencies trimmed to only reference instances within this set.
# ---------------------------------------------------------------------------
SEED_INSTANCES = [
    # ---- Layer 0: Leaves (0 deps) ----
    {
        "name": "base-vpc",
        "repo_class": "hmd-vpc",
        "version": "0.2.37",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "azs": ["us-west-2a", "us-west-2b"],
        },
        "dependencies": {},
        # BACON discovery (NERD0013): what 07_repo_classes / 12_mcp search for.
        "discovery": {
            "summary": "Provisions the base VPC and its subnets for an account.",
            "entry_points": [
                {"path": "src/cdktf/vpc.py", "description": "VPC stack entry point."}
            ],
            "capabilities": [
                {
                    "name": "create_vpc",
                    "kind": "operation",
                    "description": "Create the VPC and subnets.",
                    "location": "src/cdktf/vpc.py:12",
                },
                {
                    "name": "GET /apiop/vpc_status",
                    "kind": "endpoint",
                    "description": "Report the VPC provisioning status.",
                },
            ],
            "related_docs": [{"title": "VPC guide", "path": "docs/index.rst"}],
        },
    },
    {
        "name": "base-datadog",
        "repo_class": "hmd-inf-datadog",
        "version": "0.1.22",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {},
        "dependencies": {},
        "discovery": {
            "summary": "Ships log retention and metrics collection to Datadog.",
            "capabilities": [
                {
                    "name": "hmd datadog rotate-logs",
                    "kind": "cli_command",
                    "description": "Rotates and prunes log files past the retention window.",
                    "location": "src/python/datadog/cli.py:40",
                }
            ],
        },
    },
    {
        "name": "trino-storage",
        "repo_class": "hmd-inf-s3bucket",
        "version": "0.1.14",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {},
        "dependencies": {},
    },
    {
        "name": "device-lib",
        "repo_class": "hmd-inf-s3bucket",
        "version": "0.1.14",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {"expiration_days": 3650},
        "dependencies": {},
    },
    {
        "name": "inst-dispatcher",
        "repo_class": "hmd-lib-dispatch",
        "version": "0.1.52",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "batch_size": 15,
            "lambda_timeout": 300,
            "delivery_delay": "0",
        },
        "dependencies": {},
    },
    # ---- Layer 1: Low deps (1-2) ----
    {
        "name": "global-graph",
        "repo_class": "hmd-inf-neptune",
        "version": "0.3.23",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {"instance_size": "db.t3.medium"},
        "dependencies": {"base-vpc": "base-vpc"},
    },
    {
        "name": "eks-upg",
        "repo_class": "hmd-inf-eks-cluster",
        "version": "0.7.111",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "enable_irsa": True,
            "cluster_log_types": [],
            "enable_private_access": True,
            "enable_public_access": True,
        },
        "dependencies": {
            "base-vpc": "base-vpc",
            "neptune-db": "global-graph",
        },
    },
    {
        "name": "eks-ctrl-lin",
        "repo_class": "hmd-inf-eks-node-group",
        "version": "0.2.80",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "disk_size": 128,
            "capacity_type": "ON_DEMAND",
            "ami_type": "AL2023_x86_64_STANDARD",
            "instance_type": ["t3.xlarge", "m5.large", "m5.xlarge"],
            "scaling_config": {
                "desired_size": 2,
                "min_size": 1,
                "max_size": 4,
            },
        },
        "dependencies": {
            "base-vpc": "base-vpc",
            "eks-cluster": "eks-upg",
        },
    },
    {
        "name": "eks-alb",
        "repo_class": "hmd-inf-eks-alb",
        "version": "0.3.88",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {},
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-cluster": "eks-upg",
        },
    },
    {
        "name": "ext-secrets",
        "repo_class": "hmd-inf-ext-secrets",
        "version": "0.2.48",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {},
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-cluster": "eks-upg",
        },
    },
    {
        "name": "otel",
        "repo_class": "hmd-inf-otel-collector",
        "version": "0.1.158",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "datadog": {"enabled": True, "secretName": "datadog-api-key"},
            "protocol_version": "HTTP1",
        },
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-alb": "eks-alb",
            "ext-secrets": "ext-secrets",
        },
    },
    {
        "name": "redis",
        "repo_class": "hmd-inf-redis",
        "version": "0.1.34",
        "status": "DEPLOYED",
        "auto_deploy": "true",
        "instance_configuration": {},
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-cluster": "eks-upg",
            "ext-secrets": "ext-secrets",
        },
    },
    # ---- Layer 2: Mid-tier (3-6 deps) ----
    {
        "name": "authorizer",
        "repo_class": "hmd-inf-opa-authorizer",
        "version": "0.1.59",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {},
        "dependencies": {
            "base-vpc": "base-vpc",
            "otel-collector": "otel",
            "redis": "redis",
        },
    },
    {
        "name": "hive-metastore",
        "repo_class": "hmd-inf-hive-metastore",
        "version": "0.2.70",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "image": {"pullPolicy": "IfNotPresent"},
            "ingress": {"create": True},
        },
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-alb": "eks-alb",
            "ext-secrets": "ext-secrets",
        },
    },
    {
        "name": "explorer",
        "repo_class": "hmd-inf-superset",
        "version": "0.5.228",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "extraEnv": {"SHOW_PROGRESS": "show"},
        },
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-alb": "eks-alb",
            "ext-secrets": "ext-secrets",
            "redis": "redis",
        },
    },
    # ---- Layer 3: Heavy hubs ----
    {
        "name": "trino",
        "repo_class": "hmd-inf-trino",
        "version": "0.1.204",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "server": {"workers": 1},
        },
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-alb": "eks-alb",
            "ext-secrets": "ext-secrets",
            "graph-db": "global-graph",
            "metastore": "hive-metastore",
            "otel": "otel",
        },
    },
    {
        "name": "airflow",
        "repo_class": "hmd-app-airflow",
        "version": "0.4.316",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {},
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-alb": "eks-alb",
            "eks-cluster": "eks-upg",
            "ext-secrets": "ext-secrets",
            "neptune": "global-graph",
            "otel": "otel",
            "redis": "redis",
            "trino": "trino",
        },
    },
    {
        "name": "ms-transform",
        "repo_class": "hmd-ms-transform",
        "version": "1.0.833",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {
            "inst_worker": {"concurrency": 5},
        },
        "dependencies": {
            "airflow": "airflow",
            "authorizer": "authorizer",
            "base-vpc": "base-vpc",
            "buckets": ["trino-storage", "device-lib"],
            "compute": "eks-ctrl-lin",
            "eks-alb": "eks-alb",
            "eks-cluster": "eks-upg",
            "ext-secrets": "ext-secrets",
            "inst-dispatcher": "inst-dispatcher",
            "neptune-db": "global-graph",
            "otel-collector": "otel",
            "redis": "redis",
        },
    },
    # ---- FAILED instances ----
    {
        "name": "core-rds",
        "repo_class": "hmd-postgres-rds",
        "version": "0.4.47",
        "status": "FAILED",
        "auto_deploy": "false",
        "instance_configuration": {
            "engine_version": "14.17",
            "engine_mode": "provisioned",
            "instance_size": "db.t3.medium",
        },
        "dependencies": {
            "base-vpc": "base-vpc",
        },
    },
    {
        "name": "dns-addon",
        "repo_class": "hmd-inf-coredns-addon",
        "version": "0.1.2",
        "status": "FAILED",
        "auto_deploy": "false",
        "instance_configuration": {},
        "dependencies": {
            "compute": "eks-ctrl-lin",
            "eks-cluster": "eks-upg",
        },
    },
    # ---- Extra leaves for diversity (hmd-ms-*, hmd-database-account) ----
    {
        "name": "ms-case",
        "repo_class": "hmd-ms-case",
        "version": "0.1.56",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {"memory_size": 256},
        "dependencies": {
            "authorizer": "authorizer",
            "base-vpc": "base-vpc",
        },
    },
    {
        "name": "dbaccount-transform",
        "repo_class": "hmd-database-account",
        "version": "0.1.3",
        "status": "DEPLOYED",
        "auto_deploy": "false",
        "instance_configuration": {"db_name": "transform"},
        "dependencies": {
            "database-instance": "core-rds",
        },
    },
]


class DeploymentSeed:
    """Clear and seed the deployment service with test data."""

    def wait_for_deployment_service(self, timeout=60):
        """Wait for the deployment service API to respond."""
        deadline = time.time() + int(timeout)
        last_err = None
        # This service has no /api/health; a GET on a stable read-only apiop returning
        # 200 is a reliable readiness signal (and confirms the resource model is up).
        probe = f"{DEPLOYMENT_API}/apiop/list_resource_definitions"
        while time.time() < deadline:
            try:
                resp = urllib.request.urlopen(
                    urllib.request.Request(probe), timeout=5
                )
                if resp.status == 200:
                    return
            except Exception as e:
                last_err = e
            time.sleep(2)
        raise RuntimeError(
            f"Deployment service not ready after {timeout}s: {last_err}"
        )

    def _run_db_sql(self, sql):
        """Run a SQL statement against the deployment database."""
        result = subprocess.run(
            [
                "docker", "exec", DB_CONTAINER,
                "psql", "-U", DB_USER, "-d", DB_NAME, "-tAc", sql,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"SQL failed: {result.stderr}")
        return result.stdout.strip()

    def clear_and_seed(self):
        """Clear and seed with a PostgreSQL advisory lock to prevent races.

        When pabot runs multiple workers, each executes __init__.robot
        concurrently. Without locking, all workers seed simultaneously,
        creating duplicate entities that cause assertion errors in the
        deployment service.
        """
        lock_sql = (
            "SELECT pg_try_advisory_lock(12345);"
        )
        got_lock = self._run_db_sql(lock_sql)
        if got_lock != "t":
            # Another worker is seeding; wait for it to finish
            print("Another worker is seeding, waiting for advisory lock...")
            self._run_db_sql("SELECT pg_advisory_lock(12345);")
            # Lock acquired means the other worker finished; release and return
            self._run_db_sql("SELECT pg_advisory_unlock(12345);")
            print("Other worker finished seeding.")
            return

        try:
            self.clear_deployment_database()
            self.seed_deployment_data()
        finally:
            self._run_db_sql("SELECT pg_advisory_unlock(12345);")

    def clear_deployment_database(self):
        """Truncate data tables in the deployment DB, preserving alembic migration state."""
        sql = (
            "DO $$ DECLARE r RECORD; BEGIN "
            "FOR r IN (SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename != 'alembic_version') LOOP "
            "EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE'; "
            "END LOOP; END $$;"
        )
        result = subprocess.run(
            [
                "docker", "exec", DB_CONTAINER,
                "psql", "-U", DB_USER, "-d", DB_NAME, "-c", sql,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to clear deployment DB: {result.stderr}"
            )

    def seed_deployment_data(self):
        """Create test entities via the deployment service REST API.

        Uses SEED_INSTANCES to create a realistic BOM with real repo classes,
        versions, dependencies, and instance configurations.
        """
        # 1. Create environment
        env = self._put_entity("hmd_lang_deployment.environment", {
            "type": "dev",
            "account_number": "123456789012",
            "hmd_region": "us-west-2",
        })
        env_id = env["identifier"]

        # Track created entities to avoid duplicates and enable dep linking
        repo_class_ids = {}   # repo_class_name -> identifier
        instance_ids = {}     # instance_name -> identifier

        # 2. First pass: create all entities and basic relationships
        for inst in SEED_INSTANCES:
            rc_name = inst["repo_class"]
            version = inst["version"]

            # Create repo class (deduplicate by name)
            if rc_name not in repo_class_ids:
                rc = self._put_entity("hmd_lang_deployment.repo_class", {
                    "repo_class_name": rc_name,
                })
                repo_class_ids[rc_name] = rc["identifier"]
            rc_id = repo_class_ids[rc_name]

            # Create repo class version (unique per class+version combo). The
            # CRUD PUT carries mapping attributes as base64-encoded JSON (the
            # request model types them as str), so discovery is encoded here;
            # add_repo_class_version would accept plain JSON but also creates
            # the class/version pair, which this seed wires by hand.
            rcv_body = {"version": version}
            if inst.get("discovery"):
                rcv_body["discovery"] = _encode_mapping(inst["discovery"])
            rcv = self._put_entity("hmd_lang_deployment.repo_class_version", rcv_body)
            rcv_id = rcv["identifier"]

            # Link repo class -> version
            self._put_relationship(
                "hmd_lang_deployment.repo_class_has_repo_class_version",
                rc_id, rcv_id,
            )

            # Create repo instance
            ri = self._put_entity("hmd_lang_deployment.repo_instance", {
                "name": inst["name"],
                "auto_deploy": inst.get("auto_deploy", "false"),
            })
            ri_id = ri["identifier"]
            instance_ids[inst["name"]] = ri_id

            # Create repo instance deployment
            depl_data = {
                "deployment_id": "aaa",
                "status": inst["status"],
            }
            if inst.get("instance_configuration"):
                depl_data["instance_configuration"] = json.dumps(
                    inst["instance_configuration"]
                )
            depl = self._put_entity(
                "hmd_lang_deployment.repo_instance_deployment", depl_data,
            )
            depl_id = depl["identifier"]

            # Link environment -> instance
            self._put_relationship(
                "hmd_lang_deployment.environment_has_repo_instance",
                env_id, ri_id,
            )

            # Link instance -> class
            self._put_relationship(
                "hmd_lang_deployment.repo_instance_isa_repo_class",
                ri_id, rc_id,
            )

            # Link instance -> deployment (current)
            self._put_relationship(
                "hmd_lang_deployment.repo_instance_has_repo_instance_deployment",
                ri_id, depl_id, {"current": "true"},
            )

            # Link deployment -> version
            self._put_relationship(
                "hmd_lang_deployment.repo_instance_deployment_has_repo_class_version",
                depl_id, rcv_id,
            )

        # 3. Second pass: create dependency relationships
        for inst in SEED_INSTANCES:
            if not inst.get("dependencies"):
                continue

            from_id = instance_ids[inst["name"]]
            for role, targets in inst["dependencies"].items():
                if isinstance(targets, list):
                    for target in targets:
                        if target in instance_ids:
                            self._put_relationship(
                                "hmd_lang_deployment.repo_instance_req_repo_instance",
                                from_id, instance_ids[target], {"role": role},
                            )
                else:
                    if targets in instance_ids:
                        self._put_relationship(
                            "hmd_lang_deployment.repo_instance_req_repo_instance",
                            from_id, instance_ids[targets], {"role": role},
                        )

        # Verify seeded data
        self._verify_bom()

    def _put_entity(self, entity_type, data):
        """PUT an entity to the deployment service."""
        url = f"{DEPLOYMENT_API}/api/{entity_type}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="PUT")
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))
            if isinstance(result, dict) and "Error Message" in result:
                raise RuntimeError(
                    f"PUT {url} returned error: {result['Error Message']}"
                )
            return result
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(
                f"PUT {url} failed ({e.code}): {err_body}"
            )

    def _post_operation(self, operation, data):
        """POST to a custom operation endpoint."""
        url = f"{DEPLOYMENT_API}/apiop/{operation}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))
            if isinstance(result, dict) and "Error Message" in result:
                raise RuntimeError(
                    f"POST {url} returned error: {result['Error Message']}"
                )
            return result
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(
                f"POST {url} failed ({e.code}): {err_body}"
            )

    def _put_relationship(self, rel_type, from_id, to_id, rel_data=None):
        """Create a relationship between two entities using their identifiers."""
        url = f"{DEPLOYMENT_API}/api/{rel_type}"
        data = {"ref_from": from_id, "ref_to": to_id}
        if rel_data:
            data.update(rel_data)
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="PUT")
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))
            if isinstance(result, dict) and "Error Message" in result:
                raise RuntimeError(
                    f"PUT relationship {rel_type} returned error: {result['Error Message']}"
                )
            return result
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(
                f"PUT relationship {rel_type} failed ({e.code}): {err_body}"
            )

    def is_data_seeded(self):
        """Check whether the deployment database already has seed data.

        Queries the database directly for environment entities rather than
        using the BOM API endpoint, which fails when duplicate environments
        exist (a symptom of the race condition this check helps prevent).
        """
        try:
            count = self._run_db_sql(
                "SELECT count(*) FROM entity "
                "WHERE name = 'hmd_lang_deployment.environment';"
            )
            return int(count) == 1
        except Exception:
            return False

    def _verify_bom(self):
        """Verify the BOM endpoint returns data."""
        url = f"{DEPLOYMENT_API}/apiop/get_deployment_bom/dev"
        req = urllib.request.Request(url)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            expected = len(SEED_INSTANCES)
            if isinstance(data, list) and len(data) >= expected:
                print(f"BOM verification OK: {len(data)} items (expected {expected})")
            else:
                actual = len(data) if isinstance(data, list) else data
                print(f"WARNING: BOM returned {actual}, expected >= {expected}")
        except Exception as e:
            print(f"WARNING: BOM verification failed: {e}")
