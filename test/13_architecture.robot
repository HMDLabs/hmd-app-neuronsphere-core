*** Settings ***
Documentation     Architecture views (NERD036, hmd-cli-neuronsphere): pick a root and a
...               template, preview the model and the rendering, save the view and
...               export a documentation folder that fetches it.
...               Run this file on its own: the directory's __init__.robot clears the
...               deployment database, and this suite needs nothing cleared.
Resource          resources/common.resource
Library           resources/ArchitectureSeed.py
Suite Setup       Setup Architecture Tests
Suite Teardown    Close Test Browser
Test Tags         architecture

*** Keywords ***
Setup Architecture Tests
    ${names}=    Seed Architecture Data
    Set Suite Variable    ${NAMES}    ${names}
    Open Browser To Application
    Login As Test User

Open Preview
    Go To    ${APP_URL}/architecture/?root=${NAMES}[consumer]&template=${NAMES}[template]&version_spec=~%3D0.1&audience=customer
    Wait For Elements State    h1:has-text("Architecture")    visible    timeout=10s

*** Test Cases ***
Architecture Page Is In The Sidebar
    Navigate To Dashboard
    Click    aside >> text=Architecture
    Wait For Elements State    h1:has-text("Architecture")    visible    timeout=10s
    Get Url    ==    ${APP_URL}/architecture/

Templates Registered In The Service Are Offered
    Go To    ${APP_URL}/architecture/
    ${options}=    Get Text    select[name="template"]
    Should Contain    ${options}    ${NAMES}[template]

Preview Draws The Model And Shows The Rendering
    Open Preview
    Wait For Elements State    \#architecture-graph canvas >> nth=0    attached    timeout=15s
    ${source}=    Get Text    pre[data-output="architecture.puml"]
    Should Start With    ${source}    @startuml
    Should Contain    ${source}    ${NAMES}[consumer]
    Should Contain    ${source}    ' audience: customer

Model And Outputs Download
    Open Preview
    ${model}=    Get Attribute    a:has-text("model.json")    href
    Should Contain    ${model}    data:application/json
    ${puml}=    Get Attribute    a:has-text("architecture.puml")    href
    Should Contain    ${puml}    data:text/plain

Saving The View Lists It
    Open Preview
    Fill Text    input[name="view_name"]    ${NAMES}[view]
    Click    button:has-text("Save view")
    Wait For Elements State    text=Saved view ${NAMES}[view]    visible    timeout=10s
    Go To    ${APP_URL}/architecture/
    Wait For Elements State    \#saved-views >> text=${NAMES}[view]    visible    timeout=10s

Export Downloads A Docs Folder That Fetches The View
    Go To    ${APP_URL}/architecture/
    ${dl}=    Download    ${APP_URL}/architecture/views/${NAMES}[view]/export.zip
    Zip Should Contain    ${dl}[saveAs]    docs/index.rst    .. ns-architecture:: ${NAMES}[view]
    Zip Should Contain    ${dl}[saveAs]    README.md    HMD_DEPLOYMENT_API_URL
