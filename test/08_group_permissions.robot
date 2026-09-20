*** Settings ***
Documentation     Group-based permission tests for Okta group-to-role mapping
Resource          resources/common.resource
Library           resources/PermissionSeed.py
Suite Setup       Setup Group Permission Tests
Suite Teardown    Teardown Group Permission Tests
Test Tags         group_permissions    rbac

*** Variables ***
${GROUP_USER}           groupuser
${GROUP_PASSWORD}       grouppass123
${GROUP_EMAIL}          groupuser@test.local
${OKTA_GROUPS_JSON}     ["ns-dev-deployers", "ns-prod-viewers"]

*** Keywords ***
Setup Group Permission Tests
    [Documentation]    Create test users and open browser
    Create Test User    ${GROUP_USER}    ${GROUP_PASSWORD}    email=${GROUP_EMAIL}
    Open Browser To Application

Teardown Group Permission Tests
    [Documentation]    Clean up test users and close browser
    Delete Test User    ${GROUP_USER}
    Close Test Browser

Login As Group User
    [Documentation]    Login with the group test user
    Login As User    ${GROUP_USER}    ${GROUP_PASSWORD}

*** Test Cases ***
User With Okta-Sourced Viewer Permission Can Access Environment BOM
    [Documentation]    A user with an okta-sourced viewer permission can view the BOM
    Grant Environment Permission    ${GROUP_USER}    dev    viewer    source=okta
    Login As Group User
    Navigate To Environment    dev
    Page Should Contain Text    Bill of Materials
    Logout
    [Teardown]    Clear User Permissions    ${GROUP_USER}

User With Manual Permission Can Access Environment BOM
    [Documentation]    A user with a manually-assigned permission can view the BOM
    Grant Environment Permission    ${GROUP_USER}    dev    viewer    source=manual
    Login As Group User
    Navigate To Environment    dev
    Page Should Contain Text    Bill of Materials
    Logout
    [Teardown]    Clear User Permissions    ${GROUP_USER}

User Without Permission Is Denied Access
    [Documentation]    A user with no permissions is denied access to an environment
    Login As Group User
    Go To    ${APP_URL}/bom/dev/
    Wait For Elements State    text=don't have    visible    timeout=10s
    Logout

Okta Sync Creates Permissions From Group Mapping
    [Documentation]    Running okta group sync creates okta-sourced permissions
    Run Okta Group Sync    ${GROUP_USER}    ${OKTA_GROUPS_JSON}
    ${count}=    Get Permission Count    ${GROUP_USER}    source=okta
    Should Be True    ${count} > 0    msg=Expected okta-sourced permissions after sync

Okta Sync Replaces Only Okta-Sourced Permissions
    [Documentation]    Okta sync replaces okta permissions but preserves manual ones
    # Set up manual permission
    Grant Environment Permission    ${GROUP_USER}    test    admin    source=manual
    # Set up okta permission that will be replaced
    Grant Environment Permission    ${GROUP_USER}    dev    viewer    source=okta
    # Run sync - should replace okta permissions, keep manual
    Run Okta Group Sync    ${GROUP_USER}    ${OKTA_GROUPS_JSON}
    # Manual permission should still exist
    ${manual_count}=    Get Permission Count    ${GROUP_USER}    source=manual
    Should Be Equal As Integers    ${manual_count}    1    msg=Manual permission should be preserved
    [Teardown]    Clear User Permissions    ${GROUP_USER}

Okta Sync With Empty Groups Clears Okta Permissions
    [Documentation]    Syncing with empty group list removes all okta-sourced permissions
    Grant Environment Permission    ${GROUP_USER}    dev    deployer    source=okta
    Grant Environment Permission    ${GROUP_USER}    prod    viewer    source=okta
    Run Okta Group Sync    ${GROUP_USER}    []
    ${okta_count}=    Get Permission Count    ${GROUP_USER}    source=okta
    Should Be Equal As Integers    ${okta_count}    0    msg=Okta permissions should be cleared
    [Teardown]    Clear User Permissions    ${GROUP_USER}

Highest Role Wins When User Has Multiple Permission Sources
    [Documentation]    When user has viewer from okta and deployer manually, deployer access works
    Grant Environment Permission    ${GROUP_USER}    dev    viewer    source=okta
    Grant Environment Permission    ${GROUP_USER}    dev    deployer    source=manual
    Login As Group User
    Navigate To ChangeSet Creation
    # User should be able to access changeset creation (requires deployer role)
    Wait For Elements State    h1:has-text("Create ChangeSet")    visible    timeout=10s
    Logout
    [Teardown]    Clear User Permissions    ${GROUP_USER}

# ============== DeploymentSetPermission Tests ==============

Deployment Set Permission Can Be Granted
    [Documentation]    Granting deployment set permission creates the record
    [Tags]    group_permissions    rbac    deployment_set
    Grant Deployment Set Permission    ${GROUP_USER}    dev-test    can_deploy=True
    ${count}=    Get Deployment Set Permission Count    ${GROUP_USER}
    Should Be Equal As Integers    ${count}    1
    [Teardown]    Clear Deployment Set Permissions    ${GROUP_USER}

Deployment Set Permission Can Be Revoked
    [Documentation]    Revoking deployment set permission removes the record
    [Tags]    group_permissions    rbac    deployment_set
    Grant Deployment Set Permission    ${GROUP_USER}    dev-test    can_deploy=True
    Revoke Deployment Set Permission    ${GROUP_USER}    dev-test
    ${count}=    Get Deployment Set Permission Count    ${GROUP_USER}
    Should Be Equal As Integers    ${count}    0

User Without Deployment Set Permission Gets Error On Apply
    [Documentation]    A user without deployment set deploy permission sees error when applying
    [Tags]    group_permissions    rbac    deployment_set
    Grant Environment Permission    ${GROUP_USER}    dev    deployer    source=manual
    # Grant view-only (can_deploy=False) on the deployment set
    Grant Deployment Set Permission    ${GROUP_USER}    dev-test    can_deploy=False
    Login As Group User
    # Create a changeset targeting dev-test
    Go To    ${APP_URL}/changeset/new/
    Wait For Elements State    h1:has-text("Create ChangeSet")    visible    timeout=10s
    Fill Text    input[name="name"]    ds-perm-test
    Fill Text    input[name="deployment_set"]    dev-test
    Select Options By    select[name="environment"]    label    Dev
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    ds-perm-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Reload
    Click    a:has-text("Review & Apply")
    Wait For Elements State    h1:has-text("Review ChangeSet")    visible    timeout=10s
    # Try to apply — should get error about deployment set permissions
    Handle Future Dialogs    action=accept
    Click    button:has-text("Accept & Apply")
    Wait For Elements State    text=don't have deploy permissions for deployment set    visible    timeout=10s
    Logout
    [Teardown]    Run Keywords    Clear User Permissions    ${GROUP_USER}    AND    Clear Deployment Set Permissions    ${GROUP_USER}
