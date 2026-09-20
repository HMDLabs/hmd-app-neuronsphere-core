*** Settings ***
Documentation     Resource views (NERD0004/0006): resource definitions, resources,
...               and resource-based dependency surfacing in the Deployment GUI.
Library           Collections
Resource          resources/common.resource
Suite Setup       Setup Resource Tests
Suite Teardown    Close Test Browser
Test Tags         resources

*** Keywords ***
Setup Resource Tests
    Open Browser To Application
    Login As Test User

List Resource Names For Environment
    [Documentation]    Select ${environment} on the resources page and return the
    ...    rendered resource names (empty list on the no-match empty state).
    [Arguments]    ${environment}
    Navigate To Resources
    Select Options By    select[name="environment"]    value    ${environment}
    Click Button With Text    View
    Wait For Elements State    h1:has-text("Resources")    visible    timeout=10s
    ${names}=    Create List
    @{rows}=    Get Elements    ul li span.font-medium
    FOR    ${row}    IN    @{rows}
        ${text}=    Get Text    ${row}
        Append To List    ${names}    ${text}
    END
    RETURN    ${names}

*** Test Cases ***
Resource Definitions Page Is Accessible
    [Documentation]    The resource definitions list loads with header and filters.
    Navigate To Resource Definitions
    Wait For Elements State    h1:has-text("Resource Definitions")    visible    timeout=10s
    Wait For Elements State    input[name="namespace"]    visible
    Wait For Elements State    input[name="search"]    visible
    Wait For Elements State    button:has-text("Filter")    visible

Resource Definitions Shows Table Or Empty State
    [Documentation]    Either a definitions table or the empty-state renders.
    Navigate To Resource Definitions
    ${table}=    Get Element Count    table
    ${empty}=    Get Element Count    text=No resource definitions found.
    ${ok}=    Evaluate    ${table} > 0 or ${empty} > 0
    Should Be True    ${ok}

Resource Definitions Filters Submit
    [Documentation]    Namespace + search filters submit and are carried in the URL.
    Navigate To Resource Definitions
    Fill Text    input[name="namespace"]    kubernetes.neuronsphere.io
    Fill Text    input[name="search"]    cluster
    Click Button With Text    Filter
    Get Url    *=    namespace=kubernetes.neuronsphere.io
    Get Url    *=    search=cluster

Resource Definition Detail Renders Sections When A Definition Exists
    [Documentation]    If the catalog is seeded, opening a definition shows the
    ...    ancestry, effective schema, and producers sections. Skips when empty.
    Navigate To Resource Definitions
    ${rows}=    Get Element Count    tbody tr
    IF    ${rows} > 0
        Click    tbody tr:first-child a >> nth=0
        Wait For Elements State    h2:has-text("Inheritance (isa)")    visible    timeout=10s
        Wait For Elements State    h2:has-text("Effective Output Schema")    visible
        Wait For Elements State    h2:has-text("Producers")    visible
    END

Resources Page Is Accessible
    [Documentation]    The resources page loads with its environment picker and the
    ...    optional tag-filter inputs.
    Navigate To Resources
    Wait For Elements State    h1:has-text("Resources")    visible    timeout=10s
    Wait For Elements State    select[name="environment"]    visible
    Wait For Elements State    input[name="key"]    visible
    Wait For Elements State    input[name="value"]    visible
    Wait For Elements State    input[name="tags"]    visible

Resources Page Prompts For Environment On Load
    [Documentation]    With no environment selected, the page shows a pick-an-environment
    ...    prompt and issues no query (no results list yet).
    Navigate To Resources
    Wait For Elements State    text=Select an environment above    visible    timeout=10s
    Get Element Count    ul li    ==    0

Resources Scoped To Environment Lists Or Empties
    [Documentation]    Selecting an environment scopes the page to that environment's
    ...    resources: either resource rows or the no-match empty state, and the
    ...    pick-an-environment prompt is gone.
    Navigate To Resources
    Select Options By    select[name="environment"]    value    dev
    Click Button With Text    View
    Get Url    *=    environment=dev
    Get Element Count    text=Select an environment above    ==    0
    ${results}=    Get Element Count    ul li
    ${empty}=    Get Element Count    text=No resources match this query.
    ${ok}=    Evaluate    ${results} > 0 or ${empty} > 0
    Should Be True    ${ok}

Resources Tag Search Is Environment Scoped
    [Documentation]    A tag search within a selected environment submits carrying both
    ...    the environment and the tag key, and shows results or a no-match state.
    Navigate To Resources
    Select Options By    select[name="environment"]    value    dev
    Fill Text    input[name="key"]    tier
    Fill Text    input[name="value"]    prod
    Click Button With Text    View
    Get Url    *=    environment=dev
    Get Url    *=    key=tier
    ${results}=    Get Element Count    ul li
    ${empty}=    Get Element Count    text=No resources match this query.
    ${ok}=    Evaluate    ${results} > 0 or ${empty} > 0
    Should Be True    ${ok}

Resources Selector Search Submits With Environment
    [Documentation]    The AND selector form submits with both the environment and the
    ...    tags query param.
    Navigate To Resources
    Select Options By    select[name="environment"]    value    dev
    Fill Text    input[name="tags"]    tier=prod,region=us-west-2
    Click Button With Text    View
    Get Url    *=    environment=dev
    Get Url    *=    tags=tier%3Dprod

Resources Listing Changes When The Environment Changes
    [Documentation]    Switching environments re-scopes the listing. The service used to
    ...    drop the ``environment`` query param entirely and return the whole graph, so
    ...    every environment rendered an identical list. Needs two environments and at
    ...    least one resource to be meaningful; skips otherwise.
    Navigate To Resources
    @{options}=    Get Elements    select[name="environment"] option
    ${names}=    Create List
    FOR    ${option}    IN    @{options}
        ${value}=    Get Property    ${option}    value
        IF    "${value}" != ""
            Append To List    ${names}    ${value}
        END
    END
    ${count}=    Get Length    ${names}
    IF    ${count} < 2
        Skip    Fewer than two environments are visible to the test user.
    END
    ${first}=    Set Variable    ${names}[0]
    ${second}=    Set Variable    ${names}[1]
    ${first_rows}=    List Resource Names For Environment    ${first}
    ${second_rows}=    List Resource Names For Environment    ${second}
    ${first_len}=    Get Length    ${first_rows}
    ${second_len}=    Get Length    ${second_rows}
    IF    ${first_len} == 0 and ${second_len} == 0
        Skip    Neither environment has any deployed resources to compare.
    END
    Should Not Be Equal    ${first_rows}    ${second_rows}
    ...    msg=Environments '${first}' and '${second}' rendered an identical resource list; the environment filter is not being applied.

Resources Listing Has No Duplicate Rows
    [Documentation]    A redeployed instance used to add a second Resource row with the
    ...    same name, because superseded deployments keep status DEPLOYED. Within one
    ...    environment each resource name must appear once.
    Navigate To Resources
    ${names}=    List Resource Names For Environment    dev
    ${unique}=    Remove Duplicates    ${names}
    Should Be Equal    ${names}    ${unique}
    ...    msg=The dev resource listing contains duplicate resource names.

Sidebar Exposes Resources Navigation
    [Documentation]    The sidebar shows a Resources entry that navigates to the list.
    Navigate To Dashboard
    Click    aside >> text=Resources
    Wait For Elements State    h1:has-text("Resource Definitions")    visible    timeout=10s
    Get Url    ==    ${APP_URL}/resources/definitions/

Repo Class Detail Surfaces Resource Dependencies Column
    [Documentation]    The repo class version table gains a Resource Dependencies column.
    Navigate To Repo Classes
    ${rows}=    Get Element Count    tbody tr
    IF    ${rows} > 0
        Click    tbody tr:first-child a >> nth=0
        Wait For Elements State    th:has-text("Resource Dependencies")    visible    timeout=10s
    END
