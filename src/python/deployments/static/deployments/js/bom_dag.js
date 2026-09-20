/**
 * BOM DAG Visualization using Cytoscape.js
 *
 * Renders a directed dependency graph for environment BOM instances.
 * Nodes are uniform white rounded rectangles; only the border color encodes
 * deployment status. Nodes are expandable (tap the box) to reveal repo class/
 * version and each incoming dependency as a small "port" node on the left,
 * colored/lettered by wiring kind (resource/repo_class/instance). A dedicated
 * small button node (tap it) opens the instance detail panel.
 */

/* exported initDag, filterDagByType, resetDagFilter, zoomGraph, fitGraph, setDagDirection */
/* global cytoscape */

(function () {
    "use strict";

    var STATUS_BORDER = {
        DEPLOYED: "#16a34a",
        DEPLOY_NEXT: "#2563eb",
        FAILED: "#dc2626",
        DESTROYED: "#6b7280",
    };

    // Mirrors the wiring-kind badge colors in deployment_tags.py's _KIND_BADGES /
    // the DAG legend in bom_list.html, so a port looks like the same concept
    // wherever it appears.
    var KIND_FILL = {
        resource: "#eef2ff",
        repo_class: "#f1f5f9",
        instance: "#fffbeb",
    };
    var KIND_BORDER = {
        resource: "#a5b4fc",
        repo_class: "#cbd5e1",
        instance: "#fcd34d",
    };
    var KIND_LETTER = {
        resource: "R",
        repo_class: "C",
        instance: "I",
    };

    var DAG_DIR_BTN_BASE =
        "w-7 h-7 flex items-center justify-center text-sm border rounded";
    var DAG_DIR_BTN_ACTIVE = "bg-ns-magenta text-white border-ns-magenta";
    var DAG_DIR_BTN_INACTIVE =
        "border-gray-300 hover:bg-gray-50 text-gray-700";

    window.cy = null;
    var dagInitialized = false;
    var currentDirection = "LR";

    // Per-expanded-node bookkeeping: nodeId -> { ports: [{edge, portNode}], buttonNode }
    var expandedState = {};

    function getStatusBorder(status) {
        return STATUS_BORDER[status] || "#6b7280";
    }

    function getKindFill(kind) {
        return KIND_FILL[kind] || KIND_FILL.instance;
    }

    function getKindBorder(kind) {
        return KIND_BORDER[kind] || KIND_BORDER.instance;
    }

    function getKindLetter(kind) {
        return KIND_LETTER[kind] || KIND_LETTER.instance;
    }

    function expandNode(node) {
        if (node.hasClass("expanded")) {
            return;
        }
        var nodeId = node.id();
        var incomers = node.incomers("edge");
        var nodePos = node.position();
        var w = node.width();
        var h = node.height();

        // Persist repo class/version into the label instead of only showing it
        // transiently on hover.
        node.style(
            "label",
            node.data("label") +
                "\n" +
                node.data("repo_class") +
                " " +
                node.data("version")
        );

        var portSize = 14;
        var gap = 4;
        var startY = nodePos.y - ((incomers.length - 1) * (portSize + gap)) / 2;
        var ports = [];

        incomers.forEach(function (edge, i) {
            var role = edge.data("role");
            var kind = edge.data("kind");
            var portId = "port-" + nodeId + "-" + i;
            var portNode = window.cy.add({
                group: "nodes",
                data: { id: portId, owner: nodeId, kind: kind, role: role },
                classes: "port-node",
                position: {
                    x: nodePos.x - w / 2 - portSize / 2 - 8,
                    y: startY + i * (portSize + gap),
                },
            });
            var movedEdge = edge.move({ target: portId });
            ports.push({ edge: movedEdge, portNode: portNode });
        });

        var buttonId = "cfgbtn-" + nodeId;
        var buttonNode = window.cy.add({
            group: "nodes",
            data: { id: buttonId, owner: nodeId },
            classes: "config-btn",
            position: { x: nodePos.x + w / 2 + 10, y: nodePos.y - h / 2 },
        });

        expandedState[nodeId] = { ports: ports, buttonNode: buttonNode };
        node.addClass("expanded");
    }

    function collapseNode(node) {
        if (!node.hasClass("expanded")) {
            return;
        }
        var nodeId = node.id();
        var state = expandedState[nodeId];
        if (state) {
            state.ports.forEach(function (rec) {
                rec.edge.move({ target: nodeId });
                rec.portNode.remove();
            });
            state.buttonNode.remove();
            delete expandedState[nodeId];
        }
        node.removeClass("expanded");
        node.style("label", node.data("label"));
    }

    function toggleExpand(node) {
        if (node.hasClass("expanded")) {
            collapseNode(node);
        } else {
            expandNode(node);
        }
    }

    function collapseAllExpanded() {
        if (!window.cy) {
            return;
        }
        window.cy.nodes(".expanded").forEach(function (n) {
            collapseNode(n);
        });
    }

    function dagLayoutOptions(extra) {
        return Object.assign(
            {
                name: "dagre",
                rankDir: currentDirection,
                nodeSep: 65,
                rankSep: 100,
                padding: 30,
            },
            extra || {}
        );
    }

    function updateDirectionButtonsUI() {
        var lrBtn = document.getElementById("dag-dir-lr");
        var tbBtn = document.getElementById("dag-dir-tb");
        if (!lrBtn || !tbBtn) {
            return;
        }
        var active = currentDirection === "LR" ? lrBtn : tbBtn;
        var inactive = currentDirection === "LR" ? tbBtn : lrBtn;
        active.className = DAG_DIR_BTN_BASE + " " + DAG_DIR_BTN_ACTIVE;
        active.setAttribute("aria-pressed", "true");
        inactive.className = DAG_DIR_BTN_BASE + " " + DAG_DIR_BTN_INACTIVE;
        inactive.setAttribute("aria-pressed", "false");
    }

    window.initDag = function () {
        if (dagInitialized) {
            return;
        }

        var dagContainer = document.getElementById("bom-dag");
        if (!dagContainer) {
            return;
        }

        var dagUrl = dagContainer.dataset.dagUrl;
        if (!dagUrl) {
            return;
        }

        var cyEl = document.getElementById("cy");
        if (cyEl) {
            cyEl.innerHTML =
                '<div class="flex items-center justify-center p-8 text-gray-500 text-sm">' +
                '<svg class="animate-spin h-5 w-5 mr-2 text-ns-navy" fill="none" viewBox="0 0 24 24">' +
                '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>' +
                '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>' +
                "</svg>Loading dependency graph…</div>";
        }

        fetch(dagUrl)
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                if (data.error) {
                    document.getElementById("cy").innerHTML =
                        '<div class="p-8 text-center text-red-600">' +
                        "Failed to load DAG data: " +
                        data.error +
                        "</div>";
                    return;
                }

                window.cy = cytoscape({
                    container: document.getElementById("cy"),
                    elements: data.elements,
                    userZoomingEnabled: true,
                    userPanningEnabled: true,
                    boxSelectionEnabled: false,
                    style: [
                        {
                            selector: "node",
                            style: {
                                label: "data(label)",
                                "background-color": "#ffffff",
                                shape: "round-rectangle",
                                "font-size": "9px",
                                "text-valign": "bottom",
                                "text-margin-y": 4,
                                "text-wrap": "wrap",
                                "text-max-width": "90px",
                                width: 46,
                                height: 32,
                                "border-width": 3,
                                "border-color": function (ele) {
                                    return getStatusBorder(ele.data("status"));
                                },
                            },
                        },
                        {
                            selector: "node.port-node",
                            style: {
                                label: function (ele) {
                                    return getKindLetter(ele.data("kind"));
                                },
                                shape: "ellipse",
                                width: 14,
                                height: 14,
                                "font-size": "7px",
                                "font-weight": "bold",
                                "text-valign": "center",
                                "text-halign": "center",
                                "background-color": function (ele) {
                                    return getKindFill(ele.data("kind"));
                                },
                                "border-width": 1,
                                "border-color": function (ele) {
                                    return getKindBorder(ele.data("kind"));
                                },
                            },
                        },
                        {
                            selector: "node.config-btn",
                            style: {
                                label: "i",
                                shape: "ellipse",
                                width: 16,
                                height: 16,
                                "font-size": "9px",
                                "font-weight": "bold",
                                color: "#ffffff",
                                "text-valign": "center",
                                "text-halign": "center",
                                "background-color": "#A70B52",
                                "border-width": 0,
                            },
                        },
                        {
                            selector: "edge",
                            style: {
                                width: 1.5,
                                "line-color": "#9ca3af",
                                "target-arrow-color": "#6b7280",
                                "target-arrow-shape": "triangle",
                                "curve-style": "taxi",
                                "taxi-direction": "auto",
                                "taxi-turn": "50%",
                                "taxi-turn-min-distance": 10,
                                "arrow-scale": 0.8,
                            },
                        },
                        {
                            selector: "node:selected",
                            style: {
                                "border-color": "#A70B52",
                                "border-width": 4,
                            },
                        },
                        {
                            selector: "node.highlighted",
                            style: {
                                "border-color": "#A70B52",
                                "border-width": 3,
                                "background-opacity": 1,
                            },
                        },
                        {
                            selector: "edge.highlighted",
                            style: {
                                "line-color": "#A70B52",
                                "target-arrow-color": "#A70B52",
                                width: 2.5,
                            },
                        },
                        {
                            selector: ".dimmed",
                            style: {
                                opacity: 0.2,
                            },
                        },
                    ],
                    layout: dagLayoutOptions(),
                    minZoom: 0.2,
                    maxZoom: 3,
                    wheelSensitivity: 0.3,
                });

                // Every node from the server is a real instance node -- decorator
                // (port/button) nodes added later never get this class, so tap
                // handlers below can tell them apart via selector.
                window.cy.nodes().addClass("instance-node");

                // Tap the box -> toggle expand/collapse (repo class/version + ports).
                window.cy.on("tap", "node.instance-node", function (evt) {
                    toggleExpand(evt.target);
                });

                // Tap the dedicated button -> open the instance detail panel.
                window.cy.on("tap", "node.config-btn", function (evt) {
                    var owner = evt.target.data("owner");
                    if (owner && typeof window.showInstanceDetail === "function") {
                        window.showInstanceDetail(owner);
                    }
                });

                // Hover: highlight node and its neighborhood.
                window.cy.on("mouseover", "node", function (evt) {
                    var node = evt.target;
                    var neighborhood = node.neighborhood().add(node);
                    window.cy.elements().addClass("dimmed");
                    neighborhood.removeClass("dimmed");
                    neighborhood.addClass("highlighted");
                });

                window.cy.on("mouseout", "node", function () {
                    window.cy.elements().removeClass("dimmed highlighted");
                });

                // Populate type filter options
                var typePrefixes = {};
                window.cy.nodes(".instance-node").forEach(function (n) {
                    var tp = n.data("type_prefix");
                    if (tp) {
                        typePrefixes[tp] = (typePrefixes[tp] || 0) + 1;
                    }
                });

                var filterSelect = document.getElementById("dag-type-filter");
                if (filterSelect) {
                    // Clear existing options except the first "All" option
                    while (filterSelect.options.length > 1) {
                        filterSelect.remove(1);
                    }
                    Object.keys(typePrefixes)
                        .sort()
                        .forEach(function (tp) {
                            var opt = document.createElement("option");
                            opt.value = tp;
                            opt.textContent =
                                tp + " (" + typePrefixes[tp] + ")";
                            filterSelect.appendChild(opt);
                        });
                }

                updateDirectionButtonsUI();
                dagInitialized = true;
            })
            .catch(function (err) {
                document.getElementById("cy").innerHTML =
                    '<div class="p-8 text-center text-red-600">' +
                    "Error loading DAG: " +
                    err.message +
                    "</div>";
            });
    };

    window.filterDagByType = function (typePrefix) {
        if (!window.cy) {
            return;
        }

        // Changing the filter always collapses any expanded node rather than
        // trying to keep port/button positions in sync through a relayout.
        collapseAllExpanded();

        if (!typePrefix) {
            window.cy.elements().show();
        } else {
            window.cy.nodes(".instance-node").forEach(function (n) {
                if (n.data("type_prefix") === typePrefix) {
                    n.show();
                } else {
                    n.hide();
                }
            });
            window.cy.edges().forEach(function (e) {
                if (e.source().visible() && e.target().visible()) {
                    e.show();
                } else {
                    e.hide();
                }
            });
        }

        window.cy
            .layout(dagLayoutOptions({ animate: true, animationDuration: 300 }))
            .run();
    };

    window.resetDagFilter = function () {
        var filterSelect = document.getElementById("dag-type-filter");
        if (filterSelect) {
            filterSelect.value = "";
        }
        window.filterDagByType("");
    };

    window.setDagDirection = function (direction) {
        if (!window.cy) {
            return;
        }
        if (direction !== "LR" && direction !== "TB") {
            return;
        }
        if (direction === currentDirection) {
            return;
        }
        currentDirection = direction;

        // Expanded port/button decorator nodes are positioned in expandNode()
        // as a one-time offset relative to the parent node's position at
        // expand time; they aren't part of the dagre pass and never get
        // recomputed, so a rankDir change would leave them stranded. Collapse
        // first, same rule filterDagByType already applies before its relayout.
        collapseAllExpanded();

        updateDirectionButtonsUI();

        window.cy
            .layout(dagLayoutOptions({ animate: true, animationDuration: 300 }))
            .run();
    };

    window.zoomGraph = function (factor) {
        if (!window.cy) {
            return;
        }
        window.cy.zoom({
            level: window.cy.zoom() * factor,
            renderedPosition: {
                x: window.cy.width() / 2,
                y: window.cy.height() / 2,
            },
        });
    };

    window.fitGraph = function () {
        if (!window.cy) {
            return;
        }
        window.cy.fit(undefined, 30);
    };
})();
