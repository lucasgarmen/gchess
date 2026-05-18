from django import template

from games.i18n import t


register = template.Library()


@register.simple_tag(takes_context=True)
def tr(context, key):
    return t(context.get('current_language', 'pt'), key)
