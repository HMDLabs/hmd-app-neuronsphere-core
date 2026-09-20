*** Settings ***
Documentation     Repo classes tests for NeuronSphere Deployment GUI
Resource          resources/common.resource
Suite Setup       Setup Repo Class Tests
Suite Teardown    Close Test Browser
Test Tags         repo_classes

*** Keywords ***
Setup Repo Class Tests
    Open Browser To Application
    Login As Test User

*** Test Cases ***
Repo Classes Page Is Accessible
    [Documentation]    Verify repo classes page loads
    Navigate To Repo Classes
    Wait For Elements State    h1:has-text("Repo Classes")    visible    timeout=10s
    Wait For Elements State    text=Browse available repository classes    visible

Repo Classes Page Has Search
    [Documentation]    Verify search input is present
    Navigate To Repo Classes
    Wait For Elements State    input[name="search"]    visible    timeout=10s
    Wait For Elements State    button:has-text("Search")    visible

Repo Classes Search Submits Form
    [Documentation]    Verify search form submits
    Navigate To Repo Classes
    Fill Text    input[name="search"]    hmd-ms
    Click Button With Text    Search
    Get Url    *=    search=hmd-ms

Repo Classes Page Shows Table Or Empty State
    [Documentation]    Verify page shows either a table or empty state message
    Navigate To Repo Classes
    ${table_exists}=    Get Element Count    table
    ${empty_exists}=    Get Element Count    text=No repo classes found.
    ${has_content}=    Evaluate    ${table_exists} > 0 or ${empty_exists} > 0
    Should Be True    ${has_content}

Navigate To Repo Classes Via Sidebar
    [Documentation]    Verify sidebar navigation to repo classes works
    Navigate To Dashboard
    Click    aside >> text=Repo Classes
    Wait For Elements State    text=Browse available repository classes    visible    timeout=10s
    Get Url    ==    ${APP_URL}/repo-classes/

Repo Class Version Detail Renders Discovery And Dependencies
    [Documentation]    Clicking a version from the repo class detail page opens
    ...    its detail page showing Overview/Discovery/Dependencies sections.
    ...    Skips when the catalog has no repo classes or no versions.
    Navigate To Repo Classes
    ${rows}=    Get Element Count    tbody tr
    IF    ${rows} > 0
        Click    tbody tr:first-child a >> nth=0
        ${version_rows}=    Get Element Count    tbody tr
        IF    ${version_rows} > 0
            Click    tbody tr:first-child a >> nth=0
            Wait For Elements State    h2:has-text("Overview")    visible    timeout=10s
            Wait For Elements State    h2:has-text("Discovery")    visible
            Wait For Elements State    h2:has-text("Dependencies")    visible
        END
    END

Repo Class List Shows Summary Column
    [Documentation]    NERD004 SPEC005 / NERD0013 SPEC0001: the catalog table
    ...    carries each class's latest-version discovery summary. hmd-vpc is
    ...    seeded with one by DeploymentSeed.
    Navigate To Repo Classes
    Wait For Elements State    th:has-text("Summary")    visible    timeout=10s
    Fill Text    input[name="search"]    hmd-vpc
    Click Button With Text    Search
    Wait For Elements State    tbody tr:has-text("hmd-vpc")    visible    timeout=10s
    Wait For Elements State    tbody tr:has-text("Provisions the base VPC")    visible

Capability Search Renders Results For Seeded Capability
    [Documentation]    NERD004 SPEC005: the "Find by capability" form searches
    ...    every class's declared capabilities over HTMX and renders one row
    ...    per matching capability, linking to the version detail page. The
    ...    kind select narrows to one capability kind.
    Navigate To Repo Classes
    Wait For Elements State    h2:has-text("Find by capability")    visible    timeout=10s
    Fill Text    input[name="q"]    subnets
    Click Button With Text    Find
    Wait For HTMX Request
    Wait For Elements State    [id="capability-results"] tbody tr:has-text("create_vpc")    visible    timeout=10s
    Wait For Elements State    [id="capability-results"] tbody tr:has-text("hmd-vpc")    visible
    Wait For Elements State    [id="capability-results"] a[href*="/repo-classes/hmd-vpc/versions/"]    visible

    # Narrowing by kind drops the operation and keeps only the endpoint.
    Fill Text    input[name="q"]    vpc
    Select Options By    select[name="kind"]    value    endpoint
    Wait For HTMX Request
    Wait For Elements State    [id="capability-results"] tbody tr:has-text("vpc_status")    visible    timeout=10s
    Wait For Elements State    [id="capability-results"] tbody tr:has-text("create_vpc")    detached

Capability Search Reports No Matches
    [Documentation]    A query no capability satisfies renders the empty state,
    ...    not an error and not the whole catalog.
    Navigate To Repo Classes
    Fill Text    input[name="q"]    zzz-no-such-capability
    Click Button With Text    Find
    Wait For HTMX Request
    Wait For Elements State    [id="capability-results"] >> text=No capabilities matched    visible    timeout=10s

Version Detail Shows Capability Location
    [Documentation]    NERD004 SPEC005: the Discovery card's capability table
    ...    has a Location column carrying the manifest's path:line.
    Go To    ${APP_URL}/repo-classes/hmd-vpc/versions/0.2.37/
    Wait For Elements State    h2:has-text("Discovery")    visible    timeout=10s
    Wait For Elements State    th:has-text("Location")    visible
    Wait For Elements State    text=src/cdktf/vpc.py:12    visible
