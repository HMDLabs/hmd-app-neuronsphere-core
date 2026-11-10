Building the stylesheet
=======================

The GUI ships a precompiled Tailwind CSS v4 stylesheet,
``deployments/css/app.css``, instead of loading the Tailwind Play CDN in the
browser. The Play CDN compiled CSS in every visitor's browser on each page
load; the precompiled file is a few tens of kilobytes served by WhiteNoise.

How it is built
---------------

``hmd build`` unzips the ``hmd-config-tailwindcss-cli`` artifact (the pinned
Tailwind standalone CLI, one binary per platform) into ``src/python/css/bin/``
through ``pre_build_artifacts``, then runs ``src/python/css/build.sh`` ahead of
the ``python`` and ``docker`` steps. The script compiles
``src/python/css/app.src.css`` to
``src/python/deployments/static/deployments/css/app.css``. Neither the CSS nor
``css/bin/`` is committed.

``build.sh`` finds the CLI from ``$TAILWINDCSS``, then
``css/bin/<platform>/tailwindcss``, then ``tailwindcss`` on the ``PATH``. Set
``$TAILWINDCSS`` to build locally without ``hmd build``.

Theme and class sources
-----------------------

The NeuronSphere brand colors (``ns-*``) and the heading and body fonts are
defined in the ``@theme`` block of ``app.src.css``. Tailwind only emits classes
it finds in the ``@source`` paths: the templates, the template tags and the two
JavaScript files that build markup. A class written anywhere else (for example
in a new Python module or JavaScript file) needs its path added there.

Vendored scripts and fonts
--------------------------

No page loads code or fonts from a CDN. Pinned copies live under
``deployments/static/deployments/``:

* ``js/vendor/``: HTMX 2.0.0, Alpine.js 3.17.5, dagre 0.8.5, Cytoscape.js
  3.30.4 and cytoscape-dagre 2.5.0. To upgrade one, replace the file with the
  new release's build and update the version in ``tests/test_static_assets.py``.
* ``css/fonts.css`` and ``fonts/``: Comfortaa and Source Sans 3 (latin subset,
  ``font-display: swap``), downloaded from Google Fonts and licensed under the
  SIL Open Font License.
