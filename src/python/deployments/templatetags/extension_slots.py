"""``{% extension_slot "name" %}`` -- where an extra app renders into a core page.

The core GUI never references a premium view, template or URL name. Where a
page has a place for one -- a nav entry, a dashboard card, an action button, a
modal -- it renders a named slot instead, and every app in
``settings.EXTRA_APPS`` that ships ``<app>/slots/<name>.html`` is rendered
there in order, with the page's context. An app without that template is
skipped silently, so a slot costs the core nothing when nothing fills it.

This is the whole extension seam, together with ``DJANGO_EXTRA_APPS`` (which
appends apps and their ``urls``) and ``DEPLOYMENT_API_CLIENT_CLASS`` (which
lets an extra app widen the service client). See NERD0015 in hmd-ms-deployment.
"""

from importlib import import_module, util as importlib_util

from django import template
from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.utils.safestring import mark_safe

register = template.Library()


def slot_templates(name):
    """``(app, template)`` for every extra app shipping ``slots/<name>.html``, in app order."""
    found = []
    for app in getattr(settings, "EXTRA_APPS", []):
        try:
            found.append((app, get_template(f"{app}/slots/{name}.html")))
        except TemplateDoesNotExist:
            continue
    return found


def slot_context(app, request):
    """Extra context an app adds to its slots: ``<app>.slots.context(request)`` if it exists."""
    if importlib_util.find_spec(f"{app}.slots") is None:
        return {}
    hook = getattr(import_module(f"{app}.slots"), "context", None)
    return hook(request) if hook else {}


@register.simple_tag(takes_context=True)
def extension_slot(context, name):
    request = context.get("request")
    rendered = []
    for app, tpl in slot_templates(name):
        ctx = context.flatten()
        ctx.update(slot_context(app, request))
        rendered.append(tpl.render(ctx))
    return mark_safe("".join(rendered))
