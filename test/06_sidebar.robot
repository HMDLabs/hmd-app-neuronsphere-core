*** Settings ***
Documentation     Sidebar navigation tests for NeuronSphere Deployment GUI
Resource          resources/common.resource
Suite Setup       Setup Sidebar Tests
Suite Teardown    Close Test Browser
Test Tags         sidebar

*** Keywords ***
Setup Sidebar Tests
    Open Browser To Application
    Login As Test User

*** Test Cases ***
Sidebar Is Visible After Login
    [Documentation]    Verify sidebar is visible on the page
    Navigate To Dashboard
    Wait For Elements State    aside    visible    timeout=10s

Sidebar Has All Navigation Sections
    [Documentation]    Verify all navigation sections are present in sidebar
    Navigate To Dashboard
    Sidebar Should Show Section    Dashboard
    Sidebar Should Show Section    Environments
    Sidebar Should Show Section    Change Sets
    Sidebar Should Show Section    Repo Classes

Sidebar Dashboard Link Works
    [Documentation]    Verify clicking Dashboard in sidebar navigates correctly
    Navigate To Deployments
    Click    aside >> text=Dashboard
    Wait For Elements State    text=NeuronSphere deployment overview    visible    timeout=10s
    Get Url    ==    ${APP_URL}/

Sidebar Environments Section Has Tree
    [Documentation]    Verify environments section shows environment list
    Navigate To Dashboard
    # Click to expand environments section
    Click    aside >> button:has-text("Environments")
    Wait For Elements State    aside >> text=dev    visible    timeout=10s

Sidebar Environment Link Navigates To BOM
    [Documentation]    Verify clicking an environment in sidebar navigates to BOM
    Navigate To Dashboard
    Click    aside >> button:has-text("Environments")
    Wait For Elements State    aside >> text=dev    visible    timeout=10s
    Click    aside >> text=dev
    Get Url    *=    /bom/dev/
    Wait For Elements State    h1:has-text("Environment")    visible    timeout=10s

Sidebar Change Sets Link Works
    [Documentation]    Verify clicking Change Sets in sidebar navigates correctly
    Navigate To Dashboard
    Click    aside >> text=Change Sets
    Wait For Elements State    h1:has-text("Change Sets")    visible    timeout=10s
    Get Url    *=    /changeset/

Sidebar Repo Classes Link Works
    [Documentation]    Verify clicking Repo Classes in sidebar navigates correctly
    Navigate To Dashboard
    Click    aside >> text=Repo Classes
    Wait For Elements State    h1:has-text("Repo Classes")    visible    timeout=10s
    Get Url    ==    ${APP_URL}/repo-classes/

Sidebar Has Colored Environment Dots
    [Documentation]    Verify environments have colored status dots
    Navigate To Dashboard
    Click    aside >> button:has-text("Environments")
    Wait For Elements State    aside >> text=dev    visible    timeout=10s
    # Check that the environment entries exist with dot indicators
    Wait For Elements State    aside >> span.rounded-full >> nth=0    visible    timeout=5s

Sidebar Has No Deployments Entry On The Core Image
    [Documentation]    The Deployments section is contributed by the premium overlay through the sidebar_nav slot
    Navigate To Dashboard
    Wait For Elements State    aside    visible    timeout=10s
    Get Element Count    aside >> text=Deployments    ==    0
