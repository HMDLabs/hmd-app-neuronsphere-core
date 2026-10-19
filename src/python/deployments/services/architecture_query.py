"""The architecture model (NERD036, hmd-cli-neuronsphere) as Cytoscape elements.

Repo classes become compound parent nodes and the resources they declare sit
inside them; ``depends_on`` and ``flows_to`` edges are drawn, ``produces`` is
implied by the nesting.
"""

from typing import Any, Dict, List

DRAWN_EDGES = ("depends_on", "flows_to")


def build_architecture_elements(model: Dict[str, Any]) -> Dict[str, List[Dict]]:
    nodes = []
    ids = set()
    for node in model.get("nodes", []):
        data = {
            "id": node["id"],
            "label": node.get("label") or node["id"],
            "kind": node.get("kind", ""),
        }
        if node.get("kind") == "resource":
            data["definition"] = node.get("resource_definition", "")
        if node.get("version"):
            data["version"] = node["version"]
        if node.get("group"):
            data["parent"] = node["group"]
        nodes.append({"data": data})
        ids.add(node["id"])

    edges = []
    for i, edge in enumerate(model.get("edges", [])):
        if edge.get("kind") not in DRAWN_EDGES:
            continue
        if edge.get("from") not in ids or edge.get("to") not in ids:
            continue
        edges.append(
            {
                "data": {
                    "id": f"e{i}",
                    "source": edge["from"],
                    "target": edge["to"],
                    "kind": edge["kind"],
                    "label": edge.get("role") or "",
                    "status": edge.get("status", ""),
                }
            }
        )
    return {"nodes": nodes, "edges": edges}
