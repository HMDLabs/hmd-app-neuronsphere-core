*** Settings ***
Documentation     Dashboard tests for NeuronSphere Deployment GUI
Resource          resources/common.resource
Suite Setup       Setup Dashboard Tests
Suite Teardown    Close Test Browser
Test Tags         dashboard

*** Keywords ***
Setup Dashboard Tests
    Open Browser To Application
    Login As Test User

*** Test Cases ***
Dashboard Is Landing Page After Login
    [Documentation]    Verify dashboard is the landing page
    Navigate To Dashboard
    Wait For Elements State    h1:has-text("Dashboard")    visible    timeout=10s
    Get Url    ==    ${APP_URL}/

Dashboard Shows Environment Status Section
    [Documentation]    Verify environment status section is present
    Navigate To Dashboard
    Wait For Elements State    text=Environment Status    visible    timeout=10s

Dashboard Shows Environment Cards
    [Documentation]    Verify environment cards are displayed
    Navigate To Dashboard
    # Should show at least the environment names
    Wait For Elements State    main >> h3:has-text("dev")    visible    timeout=10s

Dashboard Environment Card Links To BOM
    [Documentation]    Verify clicking an environment card navigates to BOM
    Navigate To Dashboard
    Click    main >> h3:has-text("dev")
    Get Url    *=    /bom/dev/
    Wait For Elements State    h1:has-text("Environment")    visible    timeout=10s

Dashboard Has NeuronSphere Branding
    [Documentation]    Verify dashboard shows NeuronSphere branding
    Navigate To Dashboard
    Wait For Elements State    text=NeuronSphere deployment overview    visible    timeout=10s

Dashboard Has No Recent Deployments On The Core Image
    [Documentation]    Run observability is the premium overlay's; the core dashboard renders no such card
    Navigate To Dashboard
    Wait For Elements State    main >> h3:has-text("dev")    visible    timeout=10s
    Get Element Count    h2:has-text("Recent Deployments")    ==    0
