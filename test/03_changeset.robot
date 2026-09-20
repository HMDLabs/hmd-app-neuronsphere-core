*** Settings ***
Documentation     ChangeSet creation and management tests for NeuronSphere Deployment GUI
Resource          resources/common.resource
Suite Setup       Setup ChangeSet Tests
Suite Teardown    Close Test Browser
Test Tags         changeset

*** Keywords ***
Setup ChangeSet Tests
    Open Browser To Application
    Login As Test User

Fill ChangeSet Form
    [Arguments]    ${name}
    [Documentation]    Fills the ChangeSet creation form (name only; ChangeSets are deployment-set-agnostic)
    Fill Text    input[name="name"]    ${name}

*** Test Cases ***
ChangeSet Creation Page Accessible
    [Documentation]    Verify ChangeSet creation page is accessible
    Navigate To ChangeSet Creation
    Wait For Elements State    h1:has-text("Create ChangeSet")    visible
    Wait For Elements State    input[name="name"]    visible

ChangeSet Form Has Required Fields
    [Documentation]    Verify all required fields are present
    Navigate To ChangeSet Creation
    Wait For Elements State    input[name="name"][required]    visible

Create ChangeSet Successfully
    [Documentation]    Verify user can create a new ChangeSet
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    test-changeset-${timestamp}
    Fill ChangeSet Form    ${name}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    main >> h1:has-text("${name}")    visible    timeout=10s
    # Should redirect to draft page with draft ID
    Get Url    matches    ${APP_URL}/changeset/\\d+/

ChangeSet Draft Page Shows Name
    [Documentation]    Verify draft page shows ChangeSet name
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    draft-test-${timestamp}
    Fill ChangeSet Form    ${name}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    main >> h1:has-text("${name}")    visible    timeout=10s

ChangeSet Draft Has Add Item Form
    [Documentation]    Verify draft page has form to add items
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    add-item-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    h2:has-text("Add Instance")    visible    timeout=10s
    Wait For Elements State    input[name="instance_name"]    visible
    Wait For Elements State    input[name="repo_class"]    visible
    Wait For Elements State    input[name="version"]    visible

Add Item To ChangeSet Draft
    [Documentation]    Verify user can add an item to the draft
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    add-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    # Fill add item form
    Fill Text    input[name="instance_name"]    test-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    # Item should appear in the list
    Wait For Elements State    main >> span:has-text("test-instance")    visible    timeout=10s

Remove Item From ChangeSet Draft
    [Documentation]    Verify user can remove an item from the draft
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    remove-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    # Add an item first
    Fill Text    input[name="instance_name"]    remove-me
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    main >> span:has-text("remove-me")    visible    timeout=10s
    # Now remove it
    Handle Future Dialogs    action=accept
    Click    button[hx-post*="remove"]
    Wait For HTMX Request
    Wait For Elements State    main >> span:has-text("remove-me")    hidden    timeout=10s

Edit Dependencies Panel Loads Picker
    [Documentation]    Verify the Edit dependencies panel opens and the picker partial loads via HTMX (regression guard for the remove-dependency picker markup)
    [Tags]    changeset    dependencies
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    edit-deps-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    deps-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    main >> span:has-text("deps-instance")    visible    timeout=10s
    # Open the per-item dependency editor
    Click    button:has-text("Edit dependencies")
    Wait For Elements State    button:has-text("Save dependencies")    visible    timeout=5s
    # The HTMX-loaded picker partial replaces the loading placeholder
    Wait For Elements State    text=Loading dependency options    hidden    timeout=10s

ChangeSet Draft Shows Change Count
    [Documentation]    Verify draft shows count of changes
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    count-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    main >> h2:has-text("Changes")    visible    timeout=10s

Review Button Appears With Items
    [Documentation]    Verify Review button appears when items exist (no reload -- refreshed via HTMX OOB swap)
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    review-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    # Add an item
    Fill Text    input[name="instance_name"]    review-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    a:has-text("Review")    visible    timeout=10s

Apply And Review Actions Appear After Add Without Reload
    [Documentation]    Regression: adding the first item reveals the Apply button, Review link, and updated count via HTMX out-of-band swap -- no page reload required
    [Tags]    changeset    oob-refresh
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    oob-add-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    # Empty draft: Apply button and Review link are absent
    Wait For Elements State    button:has-text("Apply to DeploymentSet")    hidden
    Wait For Elements State    main >> h2:has-text("Changes (0)")    visible
    # Add the first item
    Fill Text    input[name="instance_name"]    oob-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    # Header actions + count refresh in place, without reloading the page
    Wait For Elements State    button:has-text("Apply to DeploymentSet")    visible    timeout=10s
    Wait For Elements State    a:has-text("Review")    visible
    Wait For Elements State    main >> h2:has-text("Changes (1)")    visible

Apply And Review Actions Hide After Removing Last Item Without Reload
    [Documentation]    Regression: removing the last item hides the Apply button and Review link via HTMX out-of-band swap -- no page reload required
    [Tags]    changeset    oob-refresh
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    oob-remove-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    last-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    button:has-text("Apply to DeploymentSet")    visible    timeout=10s
    # Remove the only item
    Handle Future Dialogs    action=accept
    Click    button[hx-post*="remove"]
    Wait For HTMX Request
    # Actions disappear and count returns to 0, without reloading the page
    Wait For Elements State    button:has-text("Apply to DeploymentSet")    hidden    timeout=10s
    Wait For Elements State    a:has-text("Review")    hidden
    Wait For Elements State    main >> h2:has-text("Changes (0)")    visible

Navigate To Review Page
    [Documentation]    Verify user can navigate to review page
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    nav-review-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    nav-review-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Reload
    Click    a:has-text("Review")
    Wait For Elements State    h1:has-text("Review ChangeSet")    visible    timeout=10s
    Get Url    matches    ${APP_URL}/changeset/\\d+/review/

Review Page Shows Summary
    [Documentation]    Verify review page shows ChangeSet summary
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    summary-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    summary-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Reload
    Click    a:has-text("Review")
    Wait For Elements State    h2:has-text("ChangeSet Summary")    visible    timeout=10s
    Wait For Elements State    main >> dd:has-text("summary-test-${timestamp}")    visible

Review Page Has Warning Message
    [Documentation]    Verify review page shows warning before apply
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    warning-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    warning-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Reload
    Click    a:has-text("Review")
    Wait For Elements State    h3:has-text("Before you proceed")    visible    timeout=10s

New ChangeSet Button On Draft Page
    [Documentation]    Verify New ChangeSet button exists on draft page
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    new-btn-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    a:has-text("New ChangeSet")    visible    timeout=10s

Click Draft In List To Edit
    [Documentation]    Verify clicking a draft in the list navigates to its edit page
    [Tags]    changeset    draft-edit
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    click-edit-${timestamp}
    Fill ChangeSet Form    ${name}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    h1:has-text("${name}")    visible    timeout=10s
    # Navigate to list and click the draft
    Navigate To ChangeSet List
    Click    a:has-text("${name}")
    Wait For Elements State    h1:has-text("${name}")    visible    timeout=10s
    Wait For Elements State    h2:has-text("Add Instance")    visible

Edit Draft After Navigating Away
    [Documentation]    Verify draft items persist after navigating away and back
    [Tags]    changeset    draft-edit
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    nav-away-${timestamp}
    Fill ChangeSet Form    ${name}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    # Add an item
    Fill Text    input[name="instance_name"]    persist-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    main >> span:has-text("persist-instance")    visible    timeout=10s
    # Navigate away to dashboard
    Navigate To Dashboard
    # Return via the list
    Navigate To ChangeSet List
    Click    a:has-text("${name}")
    Wait For Elements State    h1:has-text("${name}")    visible    timeout=10s
    # Verify the item persisted
    Wait For Elements State    main >> span:has-text("persist-instance")    visible    timeout=10s

Search And Select Existing Instance
    [Documentation]    Verify user can pick an environment then search BOM instances and pre-fill the add form
    [Tags]    changeset    instance-search
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    search-test-${timestamp}
    Click Button With Text    Create ChangeSet
    # The search panel requires an environment to be specified before the query input is usable
    Wait For Elements State    h2:has-text("Search Existing Instances")    visible    timeout=10s
    Fill Text    input[placeholder="Environment (e.g. dev)"]    dev
    Wait For Elements State    input[name="q"]:not([disabled])    visible    timeout=5s
    Fill Text    input[name="q"]    example
    Wait For HTMX Request
    ${results_selector}=    Set Variable    \#instance-search-results .instance-result
    Wait For Elements State    ${results_selector}    visible    timeout=10s
    Click    ${results_selector}:first-child
    ${instance_val}=    Get Property    input[name="instance_name"]    value
    Should Not Be Empty    ${instance_val}

# ============== Validation Tests ==============

Review Page Shows Validation Section
    [Documentation]    Verify the review page shows a validation section that loads via HTMX
    [Tags]    changeset    validation
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    validation-test-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    validation-instance
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Reload
    Click    a:has-text("Review")
    Wait For Elements State    h2:has-text("Validation")    visible    timeout=10s
    # Wait for the HTMX partial to load
    Wait For Elements State    text=Running validation checks    hidden    timeout=15s
    # Validation result should appear (either passed or warnings)
    Wait For Elements State    #validation-container >> #validation-results    visible    timeout=5s

Validation Passes For Valid ChangeSet
    [Documentation]    Verify validation passes for a well-formed changeset
    [Tags]    changeset    validation
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    Fill ChangeSet Form    valid-cs-${timestamp}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    valid-instance-${timestamp}
    Fill Text    input[name="repo_class"]    hmd-ms-test
    Fill Text    input[name="version"]    0.1.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Reload
    Click    a:has-text("Review")
    Wait For Elements State    h2:has-text("Validation")    visible    timeout=10s
    Wait For Elements State    text=Running validation checks    hidden    timeout=15s
    Wait For Elements State    text=Validation passed    visible    timeout=10s

Multiple Drafts Editable Independently
    [Documentation]    Verify two drafts can be edited independently
    [Tags]    changeset    draft-edit
    # Create draft A with item
    Navigate To ChangeSet Creation
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name_a}=    Set Variable    draft-a-${timestamp}
    Fill ChangeSet Form    ${name_a}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    instance-alpha
    Fill Text    input[name="repo_class"]    hmd-ms-alpha
    Fill Text    input[name="version"]    1.0.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    main >> span:has-text("instance-alpha")    visible    timeout=10s
    # Create draft B with different item
    Navigate To ChangeSet Creation
    ${name_b}=    Set Variable    draft-b-${timestamp}
    Fill ChangeSet Form    ${name_b}
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    instance-beta
    Fill Text    input[name="repo_class"]    hmd-ms-beta
    Fill Text    input[name="version"]    2.0.0
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    main >> span:has-text("instance-beta")    visible    timeout=10s
    # Go to list, click draft A, verify its item
    Navigate To ChangeSet List
    Click    a:has-text("${name_a}")
    Wait For Elements State    main >> span:has-text("instance-alpha")    visible    timeout=10s
    # Go to list, click draft B, verify its item
    Navigate To ChangeSet List
    Click    a:has-text("${name_b}")
    Wait For Elements State    main >> span:has-text("instance-beta")    visible    timeout=10s
