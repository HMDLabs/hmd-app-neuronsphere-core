*** Settings ***
Library     Browser    auto_closing_level=KEEP
Variables   ../robot_vars.py

*** Keywords ***
Open Browser To Application
    [Documentation]    Opens browser and navigates to the application
    New Browser    ${BROWSER}    headless=${HEADLESS}
    New Context    viewport={'width': 1920, 'height': 1080}
    New Page    ${APP_URL}

Close Test Browser
    [Documentation]    Closes all browser contexts
    Close Browser    ALL

Login As Test User
    [Documentation]    Logs in with the test user credentials
    Go To    ${APP_URL}/accounts/login/
    ${on_login_page}=    Run Keyword And Return Status
    ...    Wait For Elements State    input[name="login"]    visible    timeout=3s
    IF    ${on_login_page}
        Fill Text    input[name="login"]    ${TEST_USER}
        Fill Text    input[name="password"]    ${TEST_PASSWORD}
        # Scope to the local login form's submit; the page may also render an Okta
        # "Sign in with Okta" submit button (two submits → strict-mode violation).
        Click    form[action="/accounts/login/"] button[type="submit"]
    END
    Wait For Elements State    h1:has-text("Dashboard")    visible    timeout=10s

Login As User
    [Arguments]    ${username}    ${password}
    [Documentation]    Logs in with specified credentials
    Go To    ${APP_URL}/accounts/login/
    ${on_login_page}=    Run Keyword And Return Status
    ...    Wait For Elements State    input[name="login"]    visible    timeout=3s
    IF    ${on_login_page}
        Fill Text    input[name="login"]    ${username}
        Fill Text    input[name="password"]    ${password}
        Click    form[action="/accounts/login/"] button[type="submit"]
    END

Logout
    [Documentation]    Logs out the current user
    Click    a:has-text("Logout")
    Wait For Elements State    a:has-text("Sign In")    visible    timeout=10s

Page Should Contain Text
    [Arguments]    ${text}
    [Documentation]    Verifies page contains the specified text
    Wait For Elements State    text=${text}    visible    timeout=10s

Page Should Not Contain Text
    [Arguments]    ${text}
    [Documentation]    Verifies page does not contain the specified text
    Wait For Elements State    text=${text}    hidden    timeout=5s

Click Link With Text
    [Arguments]    ${text}
    [Documentation]    Clicks a link containing the specified text
    Click    text=${text}

Click Button With Text
    [Arguments]    ${text}
    [Documentation]    Clicks a button containing the specified text
    Click    button:has-text("${text}")

Wait For Page Load
    [Documentation]    Waits for page to finish loading
    Wait For Load State    networkidle    timeout=30s

Take Screenshot On Failure
    [Documentation]    Takes a screenshot (used for debugging)
    Take Screenshot    fullPage=True

Navigate To Dashboard
    [Documentation]    Navigates to the dashboard page
    Go To    ${APP_URL}/
    Wait For Elements State    h1:has-text("Dashboard")    visible    timeout=10s

Navigate To Environment
    [Arguments]    ${environment}
    [Documentation]    Navigates to a specific environment's BOM view
    Go To    ${APP_URL}/bom/${environment}/
    Wait For Elements State    p:has-text("Bill of Materials")    visible    timeout=10s

Navigate To Environment List
    [Documentation]    Navigates to the environment list page
    Go To    ${APP_URL}/environments/
    Wait For Elements State    h1:has-text("Environments")    visible    timeout=10s

Navigate To ChangeSet Creation
    [Documentation]    Navigates to the ChangeSet creation page
    Go To    ${APP_URL}/changeset/new/
    Wait For Elements State    h1:has-text("Create ChangeSet")    visible    timeout=10s

Navigate To ChangeSet List
    [Documentation]    Navigates to the ChangeSet list page
    Go To    ${APP_URL}/changeset/
    Wait For Elements State    h1:has-text("Change Sets")    visible    timeout=10s

Navigate To ChangeSet Draft
    [Arguments]    ${draft_id}
    [Documentation]    Navigates to a specific ChangeSet draft by ID
    Go To    ${APP_URL}/changeset/${draft_id}/
    Wait For Elements State    h2:has-text("Add Instance")    visible    timeout=10s

Navigate To Deployments
    [Documentation]    Navigates to the deployments list page
    Go To    ${APP_URL}/deployments/
    Wait For Elements State    h1:has-text("Deployments")    visible    timeout=10s

Navigate To Repo Classes
    [Documentation]    Navigates to the repo classes page
    Go To    ${APP_URL}/repo-classes/
    Wait For Elements State    h1:has-text("Repo Classes")    visible    timeout=10s

Navigate To Resource Definitions
    [Documentation]    Navigates to the resource definitions list page
    Go To    ${APP_URL}/resources/definitions/
    Wait For Elements State    h1:has-text("Resource Definitions")    visible    timeout=10s

Navigate To Resources
    [Documentation]    Navigates to the resources (tag search) page
    Go To    ${APP_URL}/resources/
    Wait For Elements State    h1:has-text("Resources")    visible    timeout=10s

Sidebar Should Show Section
    [Arguments]    ${section_text}
    [Documentation]    Verifies that the sidebar contains the specified section
    Wait For Elements State    aside >> span:text-is("${section_text}")    visible    timeout=10s

Get Table Row Count
    [Documentation]    Returns the number of rows in the BOM table
    ${count}=    Get Element Count    table tbody tr
    RETURN    ${count}

Wait For HTMX Request
    [Documentation]    Waits for HTMX requests to complete
    Wait For Load State    networkidle    timeout=10s
