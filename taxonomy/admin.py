from django.contrib import admin

from .models import TaxonomyAttribute, TaxonomyAttributeValue, TaxonomyCategory


class TaxonomyAttributeValueInline(admin.TabularInline):
    model = TaxonomyAttributeValue
    extra = 0


@admin.register(TaxonomyCategory)
class TaxonomyCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "full_path", "level")
    search_fields = ("name", "full_path")
    list_filter = ("level",)
    ordering = ("full_path",)


@admin.register(TaxonomyAttribute)
class TaxonomyAttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "handle")
    search_fields = ("name", "handle")
    filter_horizontal = ("categories",)
    inlines = [TaxonomyAttributeValueInline]


@admin.register(TaxonomyAttributeValue)
class TaxonomyAttributeValueAdmin(admin.ModelAdmin):
    list_display = ("name", "attribute")
    search_fields = ("name",)
    autocomplete_fields = ("attribute",)