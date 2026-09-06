from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0003_batchjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="bullets",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="product",
            name="collection_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="product",
            name="product_color",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="product",
            name="product_type",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="classificationresult",
            name="detected_attributes",
            field=models.JSONField(blank=True, default=list),
        ),
    ]