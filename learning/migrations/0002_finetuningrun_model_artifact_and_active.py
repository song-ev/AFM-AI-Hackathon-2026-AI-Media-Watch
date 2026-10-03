from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="finetuningrun",
            name="model_artifact",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="finetuningrun",
            name="is_active",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
