"""Unit tests for build_bom_dag_elements -- Cytoscape node/edge JSON."""
import unittest

from deployments.services.bom_query import (
    build_bom_dag_elements as _build_bom_dag_elements,
)


def _bom_item(name, repo_class, version, status="DEPLOYED", dependencies=None):
    return {
        "repo_instance_name": name,
        "repo_class_name": repo_class,
        "repo_class_version": version,
        "status": status,
        "dependencies": dependencies or {},
    }


class TestBuildBomDagElements(unittest.TestCase):
    def setUp(self):
        self.bom_data = [
            _bom_item("eks-cluster-1", "hmd-inf-eks", "1.0.0"),
            _bom_item("vpc-1", "hmd-inf-vpc", "1.0.0"),
            _bom_item(
                "svc-1",
                "hmd-ms-svc",
                "3.0.0",
                status="DEPLOY_NEXT",
                dependencies={
                    "cluster": "eks-cluster-1",
                    "network": "vpc-1",
                    "legacy": "vpc-1",
                },
            ),
            _bom_item(
                "svc-2",
                "hmd-ms-svc",
                "3.0.0",
                dependencies={"network": "vpc-1"},
            ),
        ]

    def test_nodes_include_all_bom_items(self):
        elements = _build_bom_dag_elements(self.bom_data)
        node_ids = {n["data"]["id"] for n in elements["nodes"]}
        self.assertEqual(node_ids, {"eks-cluster-1", "vpc-1", "svc-1", "svc-2"})

    def test_edges_built_directly_from_bom_dependencies(self):
        elements = _build_bom_dag_elements(self.bom_data)
        edges_by_role = {
            (e["data"]["source"], e["data"]["role"]): e["data"]
            for e in elements["edges"]
            if e["data"]["source"] == "svc-1"
        }
        self.assertEqual(edges_by_role[("svc-1", "cluster")]["target"], "eks-cluster-1")
        self.assertEqual(edges_by_role[("svc-1", "network")]["target"], "vpc-1")
        self.assertEqual(edges_by_role[("svc-1", "legacy")]["target"], "vpc-1")

    def test_edges_have_no_kind_field(self):
        """Kind classification was dropped from the DAG view entirely — no backend
        classification calls are made, so edges carry no ``kind`` data. The
        frontend (bom_dag.js) falls back to the "instance" style when absent."""
        elements = _build_bom_dag_elements(self.bom_data)
        for edge in elements["edges"]:
            self.assertNotIn("kind", edge["data"])

    def test_edges_only_created_for_targets_present_in_bom(self):
        bom_data = self.bom_data + [
            _bom_item(
                "svc-3",
                "hmd-ms-svc",
                "3.0.0",
                dependencies={"network": "not-in-bom"},
            )
        ]
        elements = _build_bom_dag_elements(bom_data)
        svc3_edges = [e for e in elements["edges"] if e["data"]["source"] == "svc-3"]
        self.assertEqual(svc3_edges, [])

    def test_no_backend_calls_needed(self):
        """_build_bom_dag_elements is a pure function of bom_data — it takes no
        client/environment and issues no backend round trips, regardless of how
        many unique (repo_class, version) pairs the BOM contains."""
        import inspect

        params = list(inspect.signature(_build_bom_dag_elements).parameters)
        self.assertEqual(params, ["bom_data"])


if __name__ == "__main__":
    unittest.main()
