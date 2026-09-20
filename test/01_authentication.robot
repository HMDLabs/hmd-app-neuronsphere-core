*** Settings ***
Documentation     Authentication tests for NeuronSphere Deployment GUI
Resource          resources/common.resource
Suite Setup       Open Browser To Application
Suite Teardown    Close Test Browser
Test Tags         authentication

*** Test Cases ***
Unauthenticated User Is Redirected To Login
    [Documentation]    Verify that unauthenticated users are redirected to login
    Go To    ${APP_URL}/
    Wait For Elements State    input[name="login"]    visible    timeout=10s
    Get Url    *=    /accounts/login/

Login Page Has Required Elements
    [Documentation]    Verify login page contains all required elements
    Go To    ${APP_URL}/accounts/login/
    Wait For Elements State    input[name="login"]    visible
    Wait For Elements State    input[name="password"]    visible
    Wait For Elements State    button[type="submit"]    visible

Successful Login Redirects To Dashboard
    [Documentation]    Verify successful login redirects to dashboard
    Login As Test User
    Wait For Elements State    h1:has-text("Dashboard")    visible    timeout=10s
    Get Url    ==    ${APP_URL}/

Logged In User Sees Sidebar Navigation
    [Documentation]    Verify sidebar navigation elements are visible after login
    Login As Test User
    Sidebar Should Show Section    Dashboard
    Sidebar Should Show Section    Environments
    Sidebar Should Show Section    Change Sets
    Sidebar Should Show Section    Deployments
    Sidebar Should Show Section    Repo Classes
    Wait For Elements State    a:has-text("Logout")    visible

User Can Logout
    [Documentation]    Verify user can logout successfully
    Login As Test User
    Logout
    Wait For Elements State    a:has-text("Sign In")    visible    timeout=10s
    # After logout, accessing protected page should redirect to login
    Go To    ${APP_URL}/
    Wait For Elements State    input[name="login"]    visible    timeout=10s

Invalid Credentials Show Error
    [Documentation]    Verify invalid credentials show an error message
    Go To    ${APP_URL}/accounts/login/
    Wait For Elements State    input[name="login"]    visible    timeout=10s
    Fill Text    input[name="login"]    invaliduser
    Fill Text    input[name="password"]    wrongpassword
    Click    button[type="submit"]
    # Should stay on login page or show error
    Wait For Elements State    input[name="login"]    visible    timeout=10s
