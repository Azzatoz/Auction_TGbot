# Generated by Django 5.0.4 on 2024-06-24 19:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auction', '0010_lot_document_userprofile_strike_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='bid',
            name='hidden',
            field=models.BooleanField(default=False),
        ),
    ]