*** Settings ***
Documentation     MCP interface tests for NeuronSphere Deployment GUI.
...
...               Protocol-level rather than browser-driven: /mcp is a JSON-RPC
...               endpoint beside Django with no pages of its own, so this suite
...               deliberately does not import resources/common.resource (which
...               loads the Browser library). It is also the acceptance check on
...               the ASGI entry point -- if the app ever falls back to WSGI, the
...               endpoint disappears and every test here fails.
Variables         robot_vars.py
Library           Collections
Library           resources/MCPSeed.py
Suite Setup       Setup Mcp Tests
Test Tags         mcp

*** Variables ***
${SEEDED_INSTANCE}      base-vpc
${RESOURCE_SCHEME}      neuronsphere://

*** Keywords ***
Setup Mcp Tests
    [Documentation]    Wait for /mcp to answer, then open one session for the suite
    Wait For Mcp Endpoint    timeout=60
    Initialize Mcp Session

*** Test Cases ***
Health Endpoint Reports The Mcp Server Built
    [Documentation]    "built" is only true in a process that came through asgi.py
    ${mcp}=    Get Mcp Health
    Should Be True    ${mcp}[enabled]
    Should Be True    ${mcp}[built]
    Should Be Equal    ${mcp}[mount_path]    /mcp
    Should Be True    ${mcp}[tools] > 0
    Should Be True    ${mcp}[resources] > 0
    Should Be True    ${mcp}[prompts] > 0

Unauthenticated Request Is Challenged
    [Documentation]    The endpoint must never be readable without a bearer token
    ${status}    ${headers}=    Mcp Request Without Authentication
    Should Be Equal As Integers    ${status}    401
    ${challenge}=    Evaluate
    ...    {k.lower(): v for k, v in $headers.items()}.get('www-authenticate', '')
    Should Contain    ${challenge}    Bearer

Tool Surface Is Advertised
    [Documentation]    Every tool the server registers is listed to the caller
    ${tools}=    List Mcp Tools
    FOR    ${name}    IN
    ...    list_environments    describe_environment    describe_instance
    ...    get_instance_dependencies    get_instance_configuration
    ...    search_repo_classes    search_capabilities    describe_repo_class
    ...    find_resource_providers    list_resource_definitions
    ...    find_resource_candidates    compare_environments
        Should Contain    ${tools}    ${name}
    END

Resources And Prompts Are Advertised
    [Documentation]    The other two halves of the protocol surface
    ${resources}=    List Mcp Resources
    Should Contain    ${resources}    ${RESOURCE_SCHEME}environments
    ${templates}=    List Mcp Resource Templates
    Should Contain    ${templates}    ${RESOURCE_SCHEME}environment/{environment}/bom
    Should Contain    ${templates}    ${RESOURCE_SCHEME}repo-classes/{repo_class_name}/discovery
    ${prompts}=    List Mcp Prompts
    Should Contain    ${prompts}    deployment_overview
    Should Contain    ${prompts}    find_capability

List Environments Returns The Seeded Environment
    [Documentation]    The entry point every environment-scoped tool depends on
    ${result}=    Call Mcp Tool    list_environments
    ${names}=    Evaluate    [e['name'] for e in $result['environments']]
    Should Contain    ${names}    ${DEFAULT_ENVIRONMENT}

Describe Environment Summarizes The Bom
    [Documentation]    The cheap overview: counts and the values to filter on
    ${result}=    Call Mcp Tool    describe_environment    environment=${DEFAULT_ENVIRONMENT}
    Should Be Equal    ${result}[detail]    summary
    Should Be True    ${result}[summary][total] > 0
    Dictionary Should Contain Key    ${result}[facets]    statuses

Describe Environment Full Detail Is Paginated
    ${result}=    Call Mcp Tool    describe_environment
    ...    environment=${DEFAULT_ENVIRONMENT}    detail=full    limit=2
    Should Be Equal    ${result}[detail]    full
    Length Should Be    ${result}[instances]    2
    Should Be Equal As Integers    ${result}[pagination][limit]    2

Describe Instance Returns Configuration And Wiring
    ${result}=    Call Mcp Tool    describe_instance
    ...    environment=${DEFAULT_ENVIRONMENT}    instance_name=${SEEDED_INSTANCE}
    Should Be Equal    ${result}[details][instance_name]    ${SEEDED_INSTANCE}
    Dictionary Should Contain Key    ${result}    configuration
    Dictionary Should Contain Key    ${result}    dependencies

Get Instance Configuration Projects And Outlines
    [Documentation]    keys_only then path -- the two-step probe of a large config
    ${outline}=    Call Mcp Tool    get_instance_configuration
    ...    environment=${DEFAULT_ENVIRONMENT}    instance_name=${SEEDED_INSTANCE}
    ...    keys_only=${TRUE}
    Should Be True    ${outline}[keys_only]
    ${keys}=    Evaluate    sorted($outline['configuration'].keys())
    Should Not Be Empty    ${keys}
    ${first}=    Set Variable    ${keys}[0]
    ${projected}=    Call Mcp Tool    get_instance_configuration
    ...    environment=${DEFAULT_ENVIRONMENT}    instance_name=${SEEDED_INSTANCE}
    ...    path=${first}
    Should Be Equal    ${projected}[path]    ${first}

Get Instance Dependencies Returns Both Directions
    ${result}=    Call Mcp Tool    get_instance_dependencies
    ...    environment=${DEFAULT_ENVIRONMENT}    instance_name=${SEEDED_INSTANCE}
    Dictionary Should Contain Key    ${result}    depends_on
    Dictionary Should Contain Key    ${result}    dependents

Repo Class Catalog Is Searchable
    ${result}=    Call Mcp Tool    search_repo_classes
    Should Be True    ${result}[pagination][total] > 0
    ${name}=    Set Variable    ${result}[repo_classes][0][repo_class_name]
    ${detail}=    Call Mcp Tool    describe_repo_class    repo_class_name=${name}
    Should Be Equal    ${detail}[repo_class_name]    ${name}
    Dictionary Should Contain Key    ${detail}    versions

Repo Class Catalog Carries The Discovery Summary
    [Documentation]    NERD008 SPEC015: search_repo_classes' description is the
    ...    latest version's BACON summary (hmd-vpc is seeded with one) and the
    ...    query matches it.
    ${result}=    Call Mcp Tool    search_repo_classes    query=Provisions the base VPC
    Should Be True    ${result}[pagination][total] >= 1
    Should Be Equal    ${result}[repo_classes][0][repo_class_name]    hmd-vpc
    Should Contain    ${result}[repo_classes][0][description]    Provisions the base VPC
    Should Be True    ${result}[repo_classes][0][capability_count] >= 2

Capability Search Returns Seeded Capability
    [Documentation]    NERD008 SPEC015: search_capabilities answers "which repo
    ...    class can do X" with one row per matching capability, and kind is
    ...    an exact filter.
    ${result}=    Call Mcp Tool    search_capabilities    query=subnets
    Should Be True    ${result}[pagination][total] >= 1
    Should Be Equal    ${result}[capabilities][0][repo_class_name]    hmd-vpc
    Should Be Equal    ${result}[capabilities][0][name]    create_vpc
    Should Be Equal    ${result}[capabilities][0][kind]    operation
    Should Be Equal    ${result}[capabilities][0][location]    src/cdktf/vpc.py:12
    Should Be Equal    ${result}[repo_classes][0][repo_class_name]    hmd-vpc

    ${cli}=    Call Mcp Tool    search_capabilities    kind=cli_command
    Should Be True    ${cli}[pagination][total] >= 1
    FOR    ${row}    IN    @{cli}[capabilities]
        Should Be Equal    ${row}[kind]    cli_command
    END

    ${message}=    Call Mcp Tool Expecting Error    search_capabilities    kind=bogus
    Should Contain    ${message}    cli_command

Repo Class Discovery Resource Is Readable
    [Documentation]    The templated resource returns one class's full
    ...    discovery block, exact-name matched -- a prefix like "hmd-vp" is
    ...    not a class.
    ${resource}=    Read Mcp Resource    ${RESOURCE_SCHEME}repo-classes/hmd-vpc/discovery
    Should Be Equal    ${resource}[repo_class_name]    hmd-vpc
    Should Contain    ${resource}[discovery][summary]    Provisions the base VPC
    Length Should Be    ${resource}[discovery][capabilities]    2
    Length Should Be    ${resource}[discovery][related_docs]    1

Find Capability Prompt Renders Its Call Order
    ${text}=    Get Mcp Prompt    find_capability    need=rotate logs
    Should Contain    ${text}    search_capabilities
    Should Contain    ${text}    describe_repo_class
    Should Contain    ${text}    rotate logs

Resource Definitions Are Listed With Their Namespaces
    ${result}=    Call Mcp Tool    list_resource_definitions
    Dictionary Should Contain Key    ${result}    definitions
    Dictionary Should Contain Key    ${result}    namespaces

Reading A Resource Returns The Same Answer As The Tool
    [Documentation]    Resources are the same authorized reads, addressed by URI
    ${tool}=    Call Mcp Tool    list_environments
    ${resource}=    Read Mcp Resource    ${RESOURCE_SCHEME}environments
    Should Be Equal As Integers    ${resource}[total]    ${tool}[total]

Reading A Templated Resource Scopes To The Environment
    ${resource}=    Read Mcp Resource
    ...    ${RESOURCE_SCHEME}environment/${DEFAULT_ENVIRONMENT}/bom
    Should Be Equal    ${resource}[environment]    ${DEFAULT_ENVIRONMENT}
    Should Be True    ${resource}[summary][total] > 0

A Prompt Renders Its Call Order
    ${text}=    Get Mcp Prompt    deployment_overview    environment=${DEFAULT_ENVIRONMENT}
    Should Contain    ${text}    describe_environment
    Should Contain    ${text}    ${DEFAULT_ENVIRONMENT}

An Unknown Environment Does Not Break The Session
    [Documentation]    A nonexistent environment must come back as a JSON-RPC
    ...    answer -- an empty BOM or a tool error, both are legitimate -- rather
    ...    than a 500 or a session the next call cannot use.
    ${result}=    Call Mcp Tool Raw    describe_environment    environment=no-such-environment
    Should Not Be Empty    ${result}
    ${tools}=    List Mcp Tools
    Should Contain    ${tools}    describe_environment

An Unknown Instance Points At Describe Environment
    ${message}=    Call Mcp Tool Expecting Error    get_instance_configuration
    ...    environment=${DEFAULT_ENVIRONMENT}    instance_name=no-such-instance
    Should Contain    ${message}    describe_environment
