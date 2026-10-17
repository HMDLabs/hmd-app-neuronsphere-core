/**
 * Architecture model (NERD036) drawn with Cytoscape.js.
 *
 * Repo classes are compound boxes holding the resources they declare; solid
 * edges are dependency roles, dashed edges are where traffic or data flows
 * (metadata.connects_to). The layout is the same dagre setup the BOM DAG uses.
 */

/* exported initArchitectureGraph */
/* global cytoscape */

(function () {
    "use strict";

    window.initArchitectureGraph = function (containerId, elementsId) {
        var source = document.getElementById(elementsId);
        var container = document.getElementById(containerId);
        if (!source || !container || typeof cytoscape === "undefined") {
            return null;
        }
        var elements = JSON.parse(source.textContent);
        return cytoscape({
            container: container,
            elements: elements.nodes.concat(elements.edges),
            wheelSensitivity: 0.2,
            style: [
                {
                    selector: "node",
                    style: {
                        label: "data(label)",
                        "font-size": 11,
                        "text-valign": "center",
                        "text-halign": "center",
                        "background-color": "#eef2ff",
                        "border-color": "#a5b4fc",
                        "border-width": 1,
                        shape: "round-rectangle",
                        width: "label",
                        height: 28,
                        padding: "8px",
                    },
                },
                {
                    selector: ":parent",
                    style: {
                        "text-valign": "top",
                        "text-halign": "center",
                        "background-color": "#f8fafc",
                        "border-color": "#94a3b8",
                        "font-weight": "bold",
                        padding: "16px",
                    },
                },
                {
                    selector: "node[kind = 'external']",
                    style: { shape: "ellipse", "background-color": "#fffbeb", "border-color": "#fcd34d" },
                },
                {
                    selector: "edge",
                    style: {
                        width: 1.5,
                        "curve-style": "bezier",
                        "target-arrow-shape": "triangle",
                        "line-color": "#64748b",
                        "target-arrow-color": "#64748b",
                        label: "data(label)",
                        "font-size": 9,
                        "text-background-color": "#ffffff",
                        "text-background-opacity": 1,
                    },
                },
                {
                    selector: "edge[kind = 'flows_to']",
                    style: { "line-style": "dashed", "line-color": "#c026d3", "target-arrow-color": "#c026d3" },
                },
                {
                    selector: "edge[status = 'candidate']",
                    style: { "line-style": "dotted", "line-color": "#f59e0b", "target-arrow-color": "#f59e0b" },
                },
            ],
            layout: { name: "dagre", rankDir: "LR", nodeSep: 30, rankSep: 80 },
        });
    };
})();
