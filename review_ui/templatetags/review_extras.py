from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dict lookup by variable key (Django templates can't use [])."""
    if not mapping:
        return None
    return mapping.get(key)