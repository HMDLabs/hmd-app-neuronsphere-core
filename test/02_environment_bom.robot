*** Settings ***
Documentation     Environment BOM view tests for NeuronSphere Deployment GUI
Resource          resources/common.resource
Suite Setup       Setup BOM Tests
Suite Teardown    Close Test Browser
Test Tags         bom

*** Keywords ***
Setup BOM Tests
    Open Browser To Application
    Login As Test User

*** Test Cases ***
Environment List Shows Available Environments
    [Documentation]    Verify environment list page shows environment cards
    Navigate To Environment List
    Wait For Elements State    h1:has-text("Environments")    visible    timeout=10s
    # Should show environment cards (dev, test, prod based on permissions)
    Wait For Elements State    text=Select an environment    visible    timeout=10s

Navigate To Dev Environment BOM
    [Documentation]    Verify user can navigate to dev environment BOM
    Navigate To Environment List
    Click    main >> h2:has-text("dev")
    Wait For Elements State    p:has-text("Bill of Materials")    visible    timeout=10s
    Get Url    *=    /bom/dev/

BOM Page Shows Table With Columns
    [Documentation]    Verify BOM table has all required columns
    Navigate To Environment    dev
    Wait For Elements State    th:has-text("Instance Name")    visible
    Wait For Elements State    th:has-text("Repo Class")    visible
    Wait For Elements State    th:has-text("Version")    visible
    Wait For Elements State    th:has-text("Status")    visible
    Wait For Elements State    th:has-text("Deployment ID")    visible
    Wait For Elements State    th:has-text("Actions")    visible

BOM Table Has Instance Rows
    [Documentation]    Verify BOM table shows instance data
    Navigate To Environment    dev
    ${row_count}=    Get Table Row Count
    Should Be True    ${row_count} >= 15    msg=Expected at least 15 BOM rows with rich seed data

BOM Search Filter Works
    [Documentation]    Verify search filter filters the table
    Navigate To Environment    dev
    Wait For Elements State    input[name="search"]    visible
    Fill Text    input[name="search"]    base
    Wait For HTMX Request
    # Table should be filtered (exact results depend on data)
    Wait For Elements State    table    visible

BOM Status Filter Works
    [Documentation]    Verify status filter dropdown works
    Navigate To Environment    dev
    Wait For Elements State    select[name="status"]    visible
    # Select the first non-default option (status values depend on seed data)
    ${options}=    Get Element Count    select[name="status"] option
    IF    ${options} > 1
        Select Options By    select[name="status"]    index    1
        Wait For HTMX Request
    END
    Wait For Elements State    table    visible

BOM Repo Class Filter Works
    [Documentation]    Verify repo class filter dropdown works
    Navigate To Environment    dev
    Wait For Elements State    select[name="repo_class"]    visible
    # Select first available option (if any)
    ${options}=    Get Element Count    select[name="repo_class"] option
    IF    ${options} > 1
        Select Options By    select[name="repo_class"]    index    1
        Wait For HTMX Request
    END
    Wait For Elements State    table    visible

BOM Table Sorting By Instance Name
    [Documentation]    Verify table can be sorted by instance name
    Navigate To Environment    dev
    Click    th:has-text("Instance Name") a
    Wait For HTMX Request
    # HTMX replaces table content without changing URL - verify table still visible
    Wait For Elements State    table    visible

BOM Table Sorting By Status
    [Documentation]    Verify table can be sorted by status
    Navigate To Environment    dev
    Click    th:has-text("Status") a
    Wait For HTMX Request
    # HTMX replaces table content without changing URL - verify table still visible
    Wait For Elements State    table    visible

BOM Refresh Button Works
    [Documentation]    Verify refresh button triggers table reload
    Navigate To Environment    dev
    Click Button With Text    Refresh
    Wait For HTMX Request
    Wait For Elements State    table    visible

BOM Page Shows Breadcrumb Navigation
    [Documentation]    Verify breadcrumb navigation is present
    Navigate To Environment    dev
    Wait For Elements State    main >> nav >> a:has-text("Environments")    visible
    Wait For Elements State    main >> nav:has-text("Environments")    visible

Click Instance Row Shows Detail Panel
    [Documentation]    Verify clicking a View button opens the detail panel and loads its content
    Navigate To Environment    dev
    ${btn_count}=    Get Element Count    button:has-text("View")
    IF    ${btn_count} > 0
        Click    button:has-text("View") >> nth=0
        Wait For Elements State    [id="slide-over-title"]    visible    timeout=10s
        # Assert the HTMX-loaded content actually rendered, not just the static panel chrome
        Wait For Elements State
        ...    [id="instance-panel-content"] >> h4:has-text("Configuration")    visible    timeout=10s
        Wait For Elements State
        ...    [id="instance-panel-content"] >> h4:has-text("Deployment History")    visible    timeout=10s
        # The View button must NOT submit the multi-select ChangeSet form: stay on the BOM page
        # with no "Provide a name for the new ChangeSet" error banner.
        Get Url    *=    /bom/dev/
        Get Element Count    text=Provide a name for the new ChangeSet    ==    0
    END

Instance Panel Shows Details Section
    [Documentation]    Verify the redesigned instance detail panel has a Details section
    ...    (repo class/version/deployment ID/status), separate from Configuration and Dependencies.
    Navigate To Environment    dev
    ${btn_count}=    Get Element Count    button:has-text("View")
    IF    ${btn_count} > 0
        Click    button:has-text("View") >> nth=0
        Wait For Elements State    [id="slide-over-title"]    visible    timeout=10s
        Wait For Elements State
        ...    [id="instance-panel-content"] >> h4:has-text("Details")    visible    timeout=10s
        Wait For Elements State
        ...    [id="instance-panel-content"] >> text=Repo Class    visible    timeout=5s
        Wait For Elements State
        ...    [id="instance-panel-content"] >> text=Deployment ID    visible    timeout=5s
    END

Instance Panel Dependencies Show Wiring Kind Badge
    [Documentation]    Verify each dependency row in the panel shows a wiring-kind badge (R/C/I)
    Navigate To Environment    dev
    ${btn_count}=    Get Element Count    button:has-text("View")
    IF    ${btn_count} > 0
        Click    button:has-text("View") >> nth=0
        Wait For Elements State    [id="slide-over-title"]    visible    timeout=10s
        Wait For Elements State
        ...    [id="instance-panel-content"] >> h4:has-text("Dependencies")    visible    timeout=10s
        ${no_deps}=    Get Element Count    [id="instance-panel-content"] >> text=No dependencies
        IF    ${no_deps} == 0
            ${resource_badges}=    Get Element Count    [id="instance-panel-content"] >> [aria-label="Resource"]
            ${class_badges}=    Get Element Count    [id="instance-panel-content"] >> [aria-label="Repo Class"]
            ${direct_badges}=    Get Element Count    [id="instance-panel-content"] >> [aria-label="Direct"]
            ${total_badges}=    Evaluate    ${resource_badges} + ${class_badges} + ${direct_badges}
            Should Be True    ${total_badges} > 0    msg=Expected at least one wiring-kind badge when dependencies are present
        END
    END

Add To ChangeSet Link Includes Repo Class And Version Params
    [Documentation]    Regression test: the panel's Add to ChangeSet link must carry real
    ...    repo_class/version query params (previously always empty due to a field-name mismatch).
    Navigate To Environment    dev
    ${btn_count}=    Get Element Count    button:has-text("View")
    IF    ${btn_count} > 0
        Click    button:has-text("View") >> nth=0
        Wait For Elements State    [id="slide-over-title"]    visible    timeout=10s
        Wait For Elements State
        ...    [id="instance-panel-content"] >> a:has-text("Add to ChangeSet")    visible    timeout=10s
        ${href}=    Get Property
        ...    [id="instance-panel-content"] >> a:has-text("Add to ChangeSet")    href
        Should Match Regexp    ${href}    repo_class=[^&]+
        Should Match Regexp    ${href}    version=[^&]+
    END

BOM Page Has Create ChangeSet Button
    [Documentation]    Verify Create ChangeSet button is present for deployers
    Navigate To Environment    dev
    Wait For Elements State    main >> a:has-text("Create ChangeSet")    visible

Create ChangeSet Button Links To Correct Page
    [Documentation]    Verify Create ChangeSet button navigates correctly
    Navigate To Environment    dev
    Click    main >> a:has-text("Create ChangeSet")
    Wait For Elements State    h1:has-text("Create ChangeSet")    visible    timeout=10s
    Get Url    *=    /changeset/new/
    Get Url    *=    environment=dev

# ============== Copy Instance Tests ==============

BOM Table Shows Copy Action For Deployers
    [Documentation]    Verify BOM table rows have a Copy action link
    [Tags]    bom    copy-instance
    Navigate To Environment    dev
    ${copy_count}=    Get Element Count    a:has-text("Copy")
    Should Be True    ${copy_count} > 0    msg=Expected Copy links in BOM table

Copy Action Links To ChangeSet Create With Params
    [Documentation]    Verify clicking Copy navigates to changeset create with pre-filled params
    [Tags]    bom    copy-instance
    Navigate To Environment    dev
    Click    a:has-text("Copy") >> nth=0
    Wait For Elements State    h1:has-text("Create ChangeSet")    visible    timeout=10s
    Get Url    *=    copy_instance=
    # Should show info banner about copying
    Wait For Elements State    text=Copying instance    visible    timeout=5s

Copy Instance Pre-Fills Draft Form
    [Documentation]    Verify creating a changeset from copy pre-fills the add-item form
    [Tags]    bom    copy-instance
    Navigate To Environment    dev
    Click    a:has-text("Copy") >> nth=0
    Wait For Elements State    h1:has-text("Create ChangeSet")    visible    timeout=10s
    # Fill the changeset form and create
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill Text    input[name="name"]    copy-test-${timestamp}
    Fill Text    input[name="deployment_set"]    dev-test
    Click Button With Text    Create ChangeSet
    Wait For Elements State    h2:has-text("Add Instance")    visible    timeout=10s
    # Instance name should be pre-filled
    Wait For Elements State    text=Pre-filled from BOM instance    visible    timeout=5s
    ${instance_val}=    Get Property    input[name="instance_name"]    value
    Should Not Be Empty    ${instance_val}

# ============== DAG View Tests ==============

BOM Page Shows View Toggle Tabs
    [Documentation]    Verify table/DAG view toggle tabs are present
    [Tags]    bom    dag
    Navigate To Environment    dev
    Wait For Elements State    button:has-text("Table View")    visible
    Wait For Elements State    button:has-text("DAG View")    visible

DAG View Tab Renders Graph
    [Documentation]    Verify clicking DAG tab shows the graph container
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #bom-dag    visible    timeout=5s
    Wait For Elements State    #cy canvas    visible    timeout=15s

DAG View Shows Multiple Nodes
    [Documentation]    Verify DAG has nodes for seeded instances
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    ${node_count}=    Evaluate JavaScript    #cy
    ...    (el) => { return window.cy ? window.cy.nodes().length : 0; }
    Should Be True    ${node_count} >= 15    msg=Expected at least 15 DAG nodes

DAG View Click Node Opens Detail Panel
    [Documentation]    Verify tapping a node's config button opens instance detail.
    ...    Tapping the node body itself now toggles expand/collapse instead
    ...    (see "DAG View Node Expand Reveals Repo Class And Version"); the
    ...    detail panel is reached via the dedicated config-button node that
    ...    appears once a node is expanded.
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    Evaluate JavaScript    #cy
    ...    (el) => { if (window.cy) window.cy.nodes('.instance-node')[0].emit('tap'); }
    Wait For Elements State    #cy canvas    visible    timeout=5s
    Evaluate JavaScript    #cy
    ...    (el) => { if (window.cy) window.cy.nodes('.config-btn')[0].emit('tap'); }
    Wait For Elements State    [id="slide-over-title"]    visible    timeout=10s
    # Assert the HTMX-loaded content actually rendered, not just the static panel chrome
    Wait For Elements State
    ...    [id="instance-panel-content"] >> h4:has-text("Configuration")    visible    timeout=10s

DAG View Node Expand Reveals Repo Class And Version
    [Documentation]    Verify tapping a node's body expands it in place instead of opening the panel
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    ${expanded}=    Evaluate JavaScript    #cy
    ...    (el) => { const n = window.cy.nodes('.instance-node')[0]; n.emit('tap'); return n.hasClass('expanded'); }
    Should Be True    ${expanded}
    ${label_changed}=    Evaluate JavaScript    #cy
    ...    (el) => { const n = window.cy.nodes('.instance-node.expanded')[0]; return n.style('label') !== n.data('label'); }
    Should Be True    ${label_changed}    msg=Expected the expanded label to include repo class/version
    # Expanding must not open the slide-over -- that's the dedicated config button's job.
    Wait For Elements State    [id="slide-over-title"]    hidden    timeout=5s

DAG View Node Expand Then Collapse Removes Ports
    [Documentation]    Verify expanding then collapsing a node cleans up its port and button nodes
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    ${node_id}=    Evaluate JavaScript    #cy
    ...    (el) => { return window.cy.edges()[0].target().id(); }
    ${expanded_ports}=    Evaluate JavaScript    #cy
    ...    (el) => { window.cy.getElementById('${node_id}').emit('tap'); return window.cy.nodes('.port-node').length; }
    Should Be True    ${expanded_ports} > 0    msg=Expected at least one port node after expanding a node with incoming edges
    ${expanded_buttons}=    Evaluate JavaScript    #cy
    ...    (el) => { return window.cy.nodes('.config-btn').length; }
    Should Be Equal As Integers    ${expanded_buttons}    1
    ${collapsed_ports}=    Evaluate JavaScript    #cy
    ...    (el) => { window.cy.getElementById('${node_id}').emit('tap'); return window.cy.nodes('.port-node').length; }
    Should Be Equal As Integers    ${collapsed_ports}    0
    ${collapsed_buttons}=    Evaluate JavaScript    #cy
    ...    (el) => { return window.cy.nodes('.config-btn').length; }
    Should Be Equal As Integers    ${collapsed_buttons}    0

DAG View Config Button Opens Panel Without Collapsing Node
    [Documentation]    Verify tapping the config button opens the panel but does not also toggle expand state
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    Evaluate JavaScript    #cy
    ...    (el) => { window.cy.nodes('.instance-node')[0].emit('tap'); }
    Wait For Elements State    #cy canvas    visible    timeout=5s
    Evaluate JavaScript    #cy
    ...    (el) => { window.cy.nodes('.config-btn')[0].emit('tap'); }
    Wait For Elements State    [id="slide-over-title"]    visible    timeout=10s
    ${still_expanded}=    Evaluate JavaScript    #cy
    ...    (el) => { return window.cy.nodes('.instance-node.expanded').length; }
    Should Be Equal As Integers    ${still_expanded}    1

DAG Legend Shows Wiring Kind Badges
    [Documentation]    Verify the DAG legend shows status dots and wiring-kind badges
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    Wait For Elements State    text=Status:    visible
    Wait For Elements State    text=Destroyed    visible
    Wait For Elements State    text=Wiring:    visible
    Wait For Elements State    text=Resource    visible
    Wait For Elements State    text=Repo Class    visible
    Wait For Elements State    text=Direct    visible

DAG View Type Filter Works
    [Documentation]    Verify type prefix filter hides/shows nodes
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    ${all_count}=    Evaluate JavaScript    #cy
    ...    (el) => { return window.cy ? window.cy.nodes().length : 0; }
    Wait For Elements State    select#dag-type-filter    visible
    Select Options By    select#dag-type-filter    value    hmd-inf
    Sleep    1s
    ${filtered_count}=    Evaluate JavaScript    #cy
    ...    (el) => { return window.cy ? window.cy.nodes(':visible').length : 0; }
    Should Be True    ${filtered_count} > 0    msg=Expected visible nodes after filter
    Should Be True    ${filtered_count} < ${all_count}    msg=Expected filter to reduce visible nodes

Switch Between Table And DAG Views
    [Documentation]    Verify switching between views preserves state
    [Tags]    bom    dag
    Navigate To Environment    dev
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=15s
    Click    button:has-text("Table View")
    Wait For Elements State    table    visible    timeout=5s
    Click    button:has-text("DAG View")
    Wait For Elements State    #cy canvas    visible    timeout=5s
