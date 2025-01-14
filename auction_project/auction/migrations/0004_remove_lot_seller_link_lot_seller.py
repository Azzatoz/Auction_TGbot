# Generated by Django 5.0.4 on 2024-06-19 09:22

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auction', '0003_seller'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='lot',
            name='seller_link',
        ),
        migrations.AddField(
            model_name='lot',
            name='seller',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='auction.seller'),
            preserve_default=False,
        ),
    ]
