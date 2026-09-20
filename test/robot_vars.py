"""Robot Framework test variables."""
import os

# Application URL.
#
# The default is the host-side address `hmd neuronsphere up` serves the GUI on:
# the environment's spare port, proxied to the k3s Ingress by hmd_proxy. 19003 is
# the *first* environment's slot -- later environments get 19007, 19011, ... -- so
# set APP_URL explicitly when running against one of those (`hmd neuronsphere env
# status` reports it). Both in-container runners override it anyway: bender passes
# the k3s node hostname and the test compose stack passes its own service name.
APP_URL = os.environ.get("APP_URL", "http://localhost:19003")

# Test credentials
TEST_USER = os.environ.get("TEST_USER", "testadmin")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "testpassword")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "test@example.com")

# Default environment for tests
DEFAULT_ENVIRONMENT = "dev"

# Browser settings
BROWSER = os.environ.get("BROWSER", "chromium")
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# Timeouts (in seconds for Robot, will be converted to ms for Playwright)
DEFAULT_TIMEOUT = 10
NAVIGATION_TIMEOUT = 30
