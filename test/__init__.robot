*** Settings ***
Documentation     Global test suite setup - seeds deployment service data
Library           resources/DeploymentSeed.py
Suite Setup       Initialize Test Data

*** Keywords ***
Initialize Test Data
    [Documentation]    Wait for services and seed test data before any tests run
    Wait For Deployment Service    timeout=60
    ${already_seeded}=    Is Data Seeded
    IF    not ${already_seeded}
        Clear And Seed
    END
