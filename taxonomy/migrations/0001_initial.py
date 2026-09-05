import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TaxonomyAttribute",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("shopify_gid", models.CharField(max_length=255, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("handle", models.CharField(blank=True, default="", max_length=255)),
                ("description", models.TextField(blank=True, default="")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TaxonomyCategory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("shopify_gid", models.CharField(max_length=255, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("full_path", models.CharField(max_length=500, unique=True)),
                ("level", models.PositiveIntegerField(default=0)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="taxonomy.taxonomycategory",
                    ),
                ),
            ],
            options={
                "ordering": ["full_path"],
                "verbose_name_plural": "taxonomy categories",
            },
        ),
        migrations.CreateModel(
            name="TaxonomyAttributeValue",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("shopify_gid", models.CharField(max_length=255, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("handle", models.CharField(blank=True, default="", max_length=255)),
                (
                    "attribute",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="values",
                        to="taxonomy.taxonomyattribute",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("attribute", "name")},
                "verbose_name_plural": "taxonomy attribute values",
            },
        ),
        migrations.CreateModel(
            name="TaxonomyAttribute_categories",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "taxonomyattribute",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="taxonomy.taxonomyattribute",
                    ),
                ),
                (
                    "taxonomycategory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="taxonomy.taxonomycategory",
                    ),
                ),
            ],
            options={"unique_together": {("taxonomyattribute", "taxonomycategory")}},
        ),
        migrations.AddField(
            model_name="taxonomyattribute",
            name="categories",
            field=models.ManyToManyField(
                blank=True,
                related_name="attributes",
                to="taxonomy.taxonomycategory",
            ),
        ),
    ]