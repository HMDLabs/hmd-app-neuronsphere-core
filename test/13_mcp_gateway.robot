*** Settings ***
Documentation     MCP gateway acceptance tests (NERD012).
...
...               The local deploy enables the gateway and registers the chart's
...               credential-free echo sidecar as one server, "echo", deployed in two
...               environments (config.mcpGatewayEndpoints: echo@dev and echo@test,
...               both auth=none since the fixture checks no token).
...
...               The same sidecar is also registered as "locked", a service-mode
...               server with no credential_ref. The local deploy has no IdP client
...               for the gateway, so "locked" must never be called: the gateway
...               fails closed rather than calling a service-mode upstream
...               anonymously (NERD012 SPEC007).
...               The echo tool reports the environment the gateway forwarded the
...               call as, so these tests prove a call reaches the deployment it
...               names -- not just that a tool answered.
...
...               The suite's key belongs to the local superuser, who may use every
...               environment. Per-user narrowing (a dev-only caller offered only
...               dev, and refused prod) is covered in-process by
...               src/python/tests/test_mcp_gateway_provider.py, which can mint
...               callers with arbitrary grants.
Variables         robot_vars.py
Library           Collections
Library           resources/MCPSeed.py
Suite Setup       Setup Gateway Tests
Test Tags         mcp    mcp-gateway

*** Variables ***
${ECHO_TOOL}      echo__echo
${LOCKED_TOOL}    locked__echo
${REGISTRY_NAME}  io.neuronsphere/echo

*** Keywords ***
Setup Gateway Tests
    Wait For Mcp Endpoint    timeout=60
    Initialize Mcp Session
    ${mcp}=    Get Mcp Health
    Should Be True    ${mcp}[gateway_enabled]    The local deploy should enable the MCP gateway

*** Test Cases ***
One Logical Server Is Advertised Across Environments
    [Documentation]    echo@dev and echo@test surface as one prefixed tool set
    ${tools}=    List Mcp Tools
    Should Contain    ${tools}    ${ECHO_TOOL}
    Should Contain    ${tools}    list_mcp_servers
    ${per_env}=    Evaluate    [t for t in $tools if 'dev' in t or 'test' in t]
    Should Be Empty    ${per_env}

The Environment Argument Offers The Callers Environments
    ${schema}=    Get Mcp Tool Schema    ${ECHO_TOOL}
    ${choices}=    Evaluate    sorted($schema['properties']['environment']['enum'])
    Should Be Equal    ${choices}    ${{['dev', 'test']}}
    List Should Contain Value    ${schema}[required]    environment
    List Should Contain Value    ${schema}[required]    text

A Call Reaches The Environment It Names
    FOR    ${environment}    IN    dev    test
        ${result}=    Call Mcp Tool    ${ECHO_TOOL}    text=hello    environment=${environment}
        Should Be Equal    ${result}[text]    hello
        Should Be Equal    ${result}[environment]    ${environment}
        Should Be Equal    ${result}[user]    ${TEST_USER}
    END

A Call Without An Environment Is Refused When There Is A Choice
    ${error}=    Call Mcp Tool Expecting Error    ${ECHO_TOOL}    text=hello
    Should Contain    ${error}    environment

A Call To An Environment Without A Deployment Is Refused
    ${error}=    Call Mcp Tool Expecting Error    ${ECHO_TOOL}    text=hello    environment=prod
    Should Contain    ${error}    not deployed in environment 'prod'

List Mcp Servers Shows The Logical Server
    ${result}=    Call Mcp Tool    list_mcp_servers
    Should Be True    ${result}[enabled]
    ${echo}=    Evaluate    next(s for s in $result['servers'] if s['server_name'] == 'echo')
    Should Be Equal    ${echo}[tool_prefix]    echo__
    Should Be Equal    ${{sorted($echo['environments'])}}    ${{['dev', 'test']}}

Registry Listing Requires A Bearer
    ${status}    ${body}=    Get Mcp Registry    authenticated=${False}
    Should Be Equal As Integers    ${status}    401

Registry Listing Is In MCP Registry Shape
    ${status}    ${body}=    Get Mcp Registry
    Should Be Equal As Integers    ${status}    200
    ${names}=    Evaluate    [e['server']['name'] for e in $body['servers']]
    Should Contain    ${names}    ${REGISTRY_NAME}
    ${status}    ${entry}=    Get Mcp Registry    path=/${REGISTRY_NAME}
    Should Be Equal As Integers    ${status}    200
    Should Be Equal    ${entry}[server][remotes][0][type]    streamable-http
    Should End With    ${entry}[server][remotes][0][url]    /mcp/

A Service Mode Server Without A Credential Is Never Called
    [Documentation]    No credential_ref and no IdP client: the gateway will not
    ...                call it anonymously, not even to list its tools, so it
    ...                offers none. The same sidecar answers as "echo" (auth=none).
    ${tools}=    List Mcp Tools
    Should Contain    ${tools}    ${ECHO_TOOL}
    Should Not Contain    ${tools}    ${LOCKED_TOOL}
