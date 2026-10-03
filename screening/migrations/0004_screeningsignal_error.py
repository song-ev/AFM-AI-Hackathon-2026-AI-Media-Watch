from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("screening", "0003_alter_screeningresult_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="screeningsignal",
            name="error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
