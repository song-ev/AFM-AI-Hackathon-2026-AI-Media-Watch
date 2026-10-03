from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deepanalysis", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="deepanalysisresult",
            name="step_errors",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
