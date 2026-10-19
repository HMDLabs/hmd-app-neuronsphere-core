Browsing Bundles and Releases
=============================

A **bundle** is a versioned grouping of repo classes that deploy together, such
as the telemetry stack. A **release** is a combination of versions that a
publisher tested and shipped; a customer's control plane receives it as its
artifacts replicate in. Both areas are read-only catalogs. They are
platform-wide, so any signed-in user can browse them; they do not depend on an
environment grant.

Bundles
-------

In the sidebar, click **Bundles** (``/bundles/``). The list shows each bundle's
latest version, how many versions exist, and its summary; use the search box to
filter by name or summary.

Open a bundle to see its versions, newest first, then open a version to see:

- **Roles** — each role the bundle declares: the suggested repo class, the
  resource it needs, whether it is required, its version spec and tag selector.
  *Provision: No (reuse only)* marks shared infrastructure that the bundle
  never deploys itself, and *Dedicated* marks a role that always gets its own
  instance rather than reusing one.
- **Configuration schema** and the default configuration.

Releases
--------

Click **Releases** (``/releases/``). Each row is a release, marked *Bundle* or
*Platform* (a platform release includes other releases), with its newest
*verified* version, newest *released* version and, on a customer's control
plane, newest *installed* version.

Open a release version to see:

- **Status and evidence.** The badge never claims more than was proved:

  *Verified*
     a gated apply of the whole environment succeeded.
  *Attested*
     an operator vouched for it with a note, shown on the page.
  *Partly attested*
     some pins were carried forward from an earlier release instead of being
     tested together. The page names each carried pin and the release it came
     from. A release that carries any pin is never shown as *Verified*.

- **Included releases**, for a platform release, each linking to its own page.
- **Pins** — repo class, version, content path and digest.
- **Tests** — the suites run against the version: outcome, passed / total
  cases, the environment they ran in and how long they took. Click a suite to
  see its cases.
- **Attestation** — the signed statement over the release description and its
  pinned builds: subject and digest, who signed it and when, the key, whether
  the signature is valid, and the materials (each pinned build and its digest).
  A version is signed when it is verified; until then the page says *Not
  signed*.
- **Release notes** for the versions that moved.
- **Arrival on this control plane.** On a customer's control plane a release
  installs itself as its artifacts replicate in. The page shows how many
  artifacts are present (*Arriving*, *Installed*, or *Blocked* when a digest
  does not match) and refreshes every five seconds until it settles.

Demo evidence
-------------

The deployment service does not record test runs or signatures yet. For a
local demo, set ``RELEASE_DEMO_EVIDENCE=true`` (chart value
``config.releaseDemoEvidence``) and versions with no recorded tests or
attestation show stand-ins, generated from the version itself, so a
publisher's and a customer's GUI show the same thing. Every stand-in is marked
**Demo data**. Recorded evidence always replaces them. Never set this in a
cloud deployment.

Cutting, promoting, shipping and planning a release, and planning a bundle, are
actions that need the premium service. A control plane that serves only the
core routes shows releases read-only.
