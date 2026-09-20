*** Settings ***
Documentation     Tests for ChangeSet BOM impact preview, accept/reject workflow, cloning, and applying to DeploymentSets
Resource          resources/common.resource
Suite Setup       Setup Advanced ChangeSet Tests
Suite Teardown    Close Test Browser
Test Tags         changeset    changeset-advanced

*** Keywords ***
Setup Advanced ChangeSet Tests
    Open Browser To Application
    Login As Test User

Create Draft With Item
    [Arguments]    ${name}    ${instance}=test-instance    ${repo_class}=hmd-ms-test    ${version}=0.1.0
    [Documentation]    Creates a ChangeSet draft and adds one item, returns on the draft page
    Navigate To ChangeSet Creation
    Fill Text    input[name="name"]    ${name}
    Fill Text    input[name="deployment_set"]    dev-test
    Select Options By    select[name="environment"]    label    Dev
    Click Button With Text    Create ChangeSet
    Wait For Elements State    input[name="instance_name"]    visible    timeout=10s
    Fill Text    input[name="instance_name"]    ${instance}
    Fill Text    input[name="repo_class"]    ${repo_class}
    Fill Text    input[name="version"]    ${version}
    Click Button With Text    Add to ChangeSet
    Wait For HTMX Request
    Wait For Elements State    main >> span:has-text("${instance}")    visible    timeout=10s

Navigate To Review For Current Draft
    [Documentation]    Clicks Review & Apply on the current draft page
    Reload
    Click    a:has-text("Review & Apply")
    Wait For Elements State    h1:has-text("Review ChangeSet")    visible    timeout=10s

*** Test Cases ***
# ============== Status Badge Tests ==============

Draft Page Shows Status Badge
    [Documentation]    Verify draft page shows the current status badge
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    status-badge-${timestamp}
    Wait For Elements State    main >> span:has-text("Draft")    visible    timeout=5s

Review Page Shows In Review Status
    [Documentation]    Verify navigating to review page sets status to In Review
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    review-status-${timestamp}
    Navigate To Review For Current Draft
    Wait For Elements State    main >> span:has-text("In Review")    visible    timeout=10s

ChangeSet List Shows Status Column
    [Documentation]    Verify the changeset list table shows status badges
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    list-status-${timestamp}
    Navigate To ChangeSet List
    Wait For Elements State    th:has-text("Status")    visible    timeout=10s
    Wait For Elements State    main >> span:has-text("Draft")    visible    timeout=5s

# ============== BOM Impact Preview Tests ==============

Review Page Loads BOM Impact Section
    [Documentation]    Verify the BOM impact preview section loads via HTMX on the review page
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    bom-impact-${timestamp}
    Navigate To Review For Current Draft
    Wait For Elements State    h2:has-text("BOM Impact Preview")    visible    timeout=10s
    # Wait for the HTMX partial to load (spinner should disappear)
    Wait For Elements State    text=Loading BOM impact analysis    hidden    timeout=15s
    # Impact summary should appear
    Wait For Elements State    span:has-text("Impact Summary")    visible    timeout=5s

BOM Impact Shows New Instance Badge
    [Documentation]    Verify new instances are tagged as NEW in the BOM impact
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    bom-new-${timestamp}    instance=unique-new-${timestamp}    repo_class=hmd-ms-unique-new
    Navigate To Review For Current Draft
    Wait For Elements State    h2:has-text("BOM Impact Preview")    visible    timeout=10s
    Wait For Elements State    text=Loading BOM impact analysis    hidden    timeout=15s
    Wait For Elements State    main >> span:has-text("NEW")    visible    timeout=10s

# ============== Reject/Reopen Workflow Tests ==============

Review Page Has Reject Button
    [Documentation]    Verify the review page has a Reject button
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    reject-btn-${timestamp}
    Navigate To Review For Current Draft
    Wait For Elements State    button:has-text("Reject")    visible    timeout=10s

Reject Opens Modal With Reason Field
    [Documentation]    Verify clicking Reject opens a modal with a textarea for reason
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    reject-modal-${timestamp}
    Navigate To Review For Current Draft
    Click    button:has-text("Reject")
    Wait For Elements State    h3:has-text("Reject ChangeSet")    visible    timeout=5s
    Wait For Elements State    textarea[name="rejection_reason"]    visible    timeout=5s

Reject ChangeSet With Reason
    [Documentation]    Verify user can reject a ChangeSet with a reason
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    reject-full-${timestamp}
    Navigate To Review For Current Draft
    Click    button:has-text("Reject")
    Wait For Elements State    textarea[name="rejection_reason"]    visible    timeout=5s
    Fill Text    textarea[name="rejection_reason"]    Version mismatch, needs 0.2.0
    Click    div[x-show="showRejectModal"] >> button:has-text("Reject ChangeSet")
    Wait For Elements State    h1:has-text("Change Sets")    visible    timeout=10s

Rejected Draft Shows Rejection Banner
    [Documentation]    Verify a rejected draft shows the rejection reason and Reopen button
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    reject-banner-${timestamp}
    Create Draft With Item    ${name}
    Navigate To Review For Current Draft
    Click    button:has-text("Reject")
    Wait For Elements State    textarea[name="rejection_reason"]    visible    timeout=5s
    Fill Text    textarea[name="rejection_reason"]    Wrong config values
    Click    div[x-show="showRejectModal"] >> button:has-text("Reject ChangeSet")
    Wait For Elements State    h1:has-text("Change Sets")    visible    timeout=10s
    # Navigate to the rejected draft
    Click    a:has-text("${name}")
    Wait For Elements State    h3:has-text("ChangeSet Rejected")    visible    timeout=10s
    Wait For Elements State    text=Wrong config values    visible    timeout=5s
    Wait For Elements State    button:has-text("Reopen")    visible    timeout=5s

Reopen Rejected ChangeSet
    [Documentation]    Verify a rejected ChangeSet can be reopened
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    reopen-test-${timestamp}
    Create Draft With Item    ${name}
    Navigate To Review For Current Draft
    Click    button:has-text("Reject")
    Wait For Elements State    textarea[name="rejection_reason"]    visible    timeout=5s
    Fill Text    textarea[name="rejection_reason"]    Needs rework
    Click    div[x-show="showRejectModal"] >> button:has-text("Reject ChangeSet")
    Wait For Elements State    h1:has-text("Change Sets")    visible    timeout=10s
    Click    a:has-text("${name}")
    Wait For Elements State    button:has-text("Reopen")    visible    timeout=10s
    Click    button:has-text("Reopen")
    Wait For Elements State    main >> span:has-text("Draft")    visible    timeout=10s
    # Rejection banner should be gone
    Wait For Elements State    h3:has-text("ChangeSet Rejected")    hidden    timeout=5s

# ============== Clone Tests ==============

Draft Page Has Clone Button
    [Documentation]    Verify the draft page has a Clone button
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    clone-btn-${timestamp}
    Wait For Elements State    button:has-text("Clone")    visible    timeout=5s

Clone ChangeSet Creates New Draft
    [Documentation]    Verify cloning creates a new draft with same content
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    clone-src-${timestamp}
    Create Draft With Item    ${name}    instance=clone-instance    repo_class=hmd-ms-clone
    Click    button:has-text("Clone")
    Wait For Elements State    h1:has-text("${name}-copy")    visible    timeout=10s
    # Cloned draft should have the same item
    Wait For Elements State    main >> span:has-text("clone-instance")    visible    timeout=10s

Clone From List Page
    [Documentation]    Verify cloning from the changeset list works
    ${timestamp}=    Evaluate    __import__('time').time()
    ${name}=    Set Variable    list-clone-${timestamp}
    Create Draft With Item    ${name}    instance=list-clone-inst
    Navigate To ChangeSet List
    # Click the Clone button in the actions column for this draft
    Click    tr:has-text("${name}") >> button:has-text("Clone")
    Wait For Elements State    h1:has-text("${name}-copy")    visible    timeout=10s
    Wait For Elements State    main >> span:has-text("list-clone-inst")    visible    timeout=10s

# ============== Apply Modal Tests ==============

# ============== Edit Instance Version Picker Tests ==============
# The Add Instance form on the same page carries inputs with the same names
# (version_q, deployment_id, version), so every selector below is scoped to the
# panel's own container -- #instance-editor-item-0 for the first Changes row.

Edit Instance Panel Opens Before Versions Load
    [Documentation]    The panel renders with no version fetch; the picker loads its own list
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    edit-lazy-${timestamp}    edit-lazy-inst
    Click    button:has-text("Edit instance")
    # The editable fields are present regardless of whether versions resolved.
    Wait For Elements State    \#instance-editor-item-0 >> input[name="deployment_id"]    visible    timeout=10s
    Wait For Elements State    \#instance-editor-item-0 >> textarea[name="instance_configuration"]    visible    timeout=10s
    Wait For Elements State    \#instance-editor-item-0 >> input[name="version_q"]    visible    timeout=10s
    # A search picker, not the old unbounded dropdown.
    Wait For Elements State    \#instance-editor-item-0 >> select[name="version"]    detached

Edit Instance Version Picker Is Scoped To Its Item
    [Documentation]    Element ids carry the item index so several panels cannot collide
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    edit-scope-${timestamp}    edit-scope-inst
    Click    button:has-text("Edit instance")
    Wait For Elements State    \#version_input_0    attached    timeout=10s
    Wait For Elements State    \#version-results-0    attached    timeout=10s

Edit Instance Keeps Current Version When Picker Untouched
    [Documentation]    Saving without choosing a version preserves the item's existing version
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    edit-keep-${timestamp}    edit-keep-inst    version=0.1.0
    Click    button:has-text("Edit instance")
    Wait For Elements State    \#instance-editor-item-0 >> input[name="deployment_id"]    visible    timeout=10s
    Fill Text    \#instance-editor-item-0 >> input[name="deployment_id"]    bbb
    Click Button With Text    Save instance
    Wait For HTMX Request
    # Version unchanged, deployment id updated.
    Wait For Elements State    main >> span:has-text("v0.1.0")    visible    timeout=10s
    Wait For Elements State    main >> span:has-text("ID: bbb")    visible    timeout=10s

Edit Instance Version Search Filters Server Side
    [Documentation]    Typing in the version box re-queries rather than filtering the rendered page
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    edit-search-${timestamp}    edit-search-inst
    Click    button:has-text("Edit instance")
    Wait For Elements State    \#instance-editor-item-0 >> input[name="version_q"]    visible    timeout=10s
    Fill Text    \#instance-editor-item-0 >> input[name="version_q"]    zzz-no-such-version
    Wait For HTMX Request
    Wait For Elements State    \#version-results-0 >> text=No versions    visible    timeout=10s

Draft Page Has No Apply Button On The Core Image
    [Documentation]    Apply is the premium overlay's changeset_actions slot; the core draft page shows Review only
    ${timestamp}=    Evaluate    __import__('time').time()
    Create Draft With Item    no-apply-${timestamp}
    Wait For Elements State    a:has-text("Review")    visible    timeout=5s
    Get Element Count    button:has-text("Apply to DeploymentSet")    ==    0
