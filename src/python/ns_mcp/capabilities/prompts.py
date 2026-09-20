"""MCP prompts -- the multi-tool workflows this surface is actually for.

Each prompt is a plain function returning the text of a user message. They hold
no credentials and read nothing, so unlike tools and resources they do not go
through ``@read_tool``: a prompt only tells the caller which tools to run and in
what order, and every one of those calls is authorized and audited when it
happens. The value is in the *order* -- summary before full, edges before
classification -- which is the same cost discipline the tool descriptions carry.
"""


def deployment_overview(environment: str) -> str:
    """Orient in an environment without pulling its whole BOM."""
    return (
        f"Give me an overview of the '{environment}' environment.\n\n"
        f"Work in this order:\n"
        f"1. describe_environment(environment='{environment}') at the default "
        f"detail='summary' -- this is one cheap call and tells you the totals, "
        f"the status breakdown, and which repo classes are present.\n"
        f"2. Only if something in the summary needs explaining, call it again "
        f"with detail='full' and a filter (status or repo_class) rather than "
        f"pulling the whole list; page with limit/offset.\n"
        f"3. For any instance that looks wrong, get_instance_dependencies "
        f"before describe_instance -- the edge query is much cheaper and often "
        f"answers the question on its own.\n\n"
        f"Report what is deployed, anything not in a healthy status, and "
        f"anything whose dependencies do not resolve within the environment."
    )


def dependency_impact(environment: str, instance_name: str) -> str:
    """Work out the blast radius of changing one instance."""
    return (
        f"What would be affected if '{instance_name}' in '{environment}' were "
        f"changed or redeployed?\n\n"
        f"1. get_instance_dependencies(environment='{environment}', "
        f"instance_name='{instance_name}', direction='both') -- 'dependents' is "
        f"the blast radius, 'depends_on' is what it needs to come back up, and "
        f"'unresolved' names targets its wiring points at that are not in this "
        f"environment's BOM.\n"
        f"2. Walk one hop out: call get_instance_dependencies again for each "
        f"dependent. Do not use describe_instance for this -- it classifies "
        f"dependency roles, which costs two extra service calls per instance.\n"
        f"3. Use describe_instance only on the instance itself, if you need the "
        f"wiring kind of a role (resource, repo_class, or instance).\n\n"
        f"Report the direct and one-hop dependents, and call out any "
        f"unresolved dependency separately -- that is usually the interesting "
        f"finding."
    )


def find_provider_for_role(resource_definition_name: str, environment: str) -> str:
    """Choose something to satisfy a resource-typed dependency role."""
    return (
        f"I need to satisfy a dependency role that requires the resource "
        f"'{resource_definition_name}' in the '{environment}' environment.\n\n"
        f"1. list_resource_definitions(query='{resource_definition_name}') to "
        f"confirm the exact namespace and version -- resource definitions are "
        f"namespaced and the short name is often ambiguous.\n"
        f"2. find_resource_candidates(environment='{environment}', "
        f"resource_definition_name='{resource_definition_name}') for what is "
        f"already deployed there and could be wired up as-is.\n"
        f"3. If there are no candidates, find_resource_providers for the repo "
        f"classes that could produce it -- that is the platform-wide catalog "
        f"answer, and tells me what I would have to deploy. Set "
        f"include_subtypes=true, since a producer of a subtype satisfies the "
        f"requirement too.\n\n"
        f"Recommend either an existing instance to wire to or a repo class to "
        f"deploy, and say which."
    )


def environment_drift(from_environment: str, to_environment: str) -> str:
    """Explain how two environments have diverged."""
    return (
        f"How have '{from_environment}' and '{to_environment}' diverged?\n\n"
        f"1. compare_environments(from_environment='{from_environment}', "
        f"to_environment='{to_environment}') at detail='summary' -- counts and "
        f"names with change flags. You need view access to both.\n"
        f"2. Call it again with detail='full' only if the configuration or "
        f"dependency deltas matter; that response is much larger.\n"
        f"3. For an instance whose version changed, describe_repo_class with "
        f"that version tells you what the newer version declares.\n\n"
        f"Summarize the drift as: what exists only in one side, what changed "
        f"version, and what changed configuration -- with the version drift "
        f"first, since that is what a deployment would act on."
    )


def find_capability(need: str) -> str:
    """Find which repo class can do something, from its discovery metadata."""
    return (
        f"Which repo class can {need}?\n\n"
        f"1. search_capabilities(query='{need}') -- every word must appear in "
        f"a class's summary, a capability name or description, or an entry "
        f"point, so if nothing matches try fewer or broader words. Add "
        f"kind='endpoint' / 'cli_command' / 'function' / 'class' / "
        f"'operation' when you know what shape of thing you need.\n"
        f"2. The 'capabilities' rows name the class, version, kind and source "
        f"location; the 'repo_classes' list is ranked and includes classes "
        f"that matched on their summary alone.\n"
        f"3. For the best candidate, describe_repo_class(repo_class_name, "
        f"version) for its full discovery block, dependency roles and default "
        f"configuration -- or read the "
        f"neuronsphere://repo-classes/{{name}}/discovery resource.\n\n"
        f"Answer with the repo class and the specific capability, and say "
        f"whether it is already deployed anywhere (describe_environment) or "
        f"would have to be."
    )


def register(mcp):
    """Register this module's prompts. Returns the names registered."""
    mcp.prompt(
        find_capability,
        name="find_capability",
        description=(
            "Find which repo class can do something, from the capabilities "
            "each class declares in its manifest."
        ),
    )
    mcp.prompt(
        deployment_overview,
        name="deployment_overview",
        description=(
            "Summarize what is deployed in an environment and what looks "
            "wrong, in the cheapest call order."
        ),
    )
    mcp.prompt(
        dependency_impact,
        name="dependency_impact",
        description=(
            "Work out the blast radius of changing one deployed instance, "
            "including unresolved dependencies."
        ),
    )
    mcp.prompt(
        find_provider_for_role,
        name="find_provider_for_role",
        description=(
            "Choose an existing instance or a repo class to satisfy a "
            "resource-typed dependency role in an environment."
        ),
    )
    mcp.prompt(
        environment_drift,
        name="environment_drift",
        description=(
            "Explain how two environments have diverged, version drift first."
        ),
    )
    return [
        "deployment_overview",
        "dependency_impact",
        "find_provider_for_role",
        "environment_drift",
        "find_capability",
    ]
