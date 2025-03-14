# Generated by Django 4.2.11 on 2024-12-09 17:36

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0006_auto_20230515_1832'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalproject',
            name='description',
            field=models.TextField(default='We do not have information about your research. Please provide a detailed description of your work.', validators=[django.core.validators.MinLengthValidator(10, 'The project description must be > 10 characters.')]),
        ),
        migrations.AlterField(
            model_name='historicalproject',
            name='title',
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='project',
            name='description',
            field=models.TextField(default='We do not have information about your research. Please provide a detailed description of your work.', validators=[django.core.validators.MinLengthValidator(10, 'The project description must be > 10 characters.')]),
        ),
        migrations.AlterField(
            model_name='project',
            name='title',
            field=models.CharField(max_length=255, unique=True),
        ),
    ]
