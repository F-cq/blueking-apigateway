# Generated by Django 3.2.18 on 2023-09-02 05:07

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0036_auto_20230902_1307'),
        ('permission', '0009_auto_20210219_2129'),
    ]

    operations = [
        migrations.RenameField(
            model_name='appapipermission',
            old_name='api',
            new_name='gateway',
        ),
        migrations.RenameField(
            model_name='apppermissionapply',
            old_name='api',
            new_name='gateway',
        ),
        migrations.RenameField(
            model_name='apppermissionapplystatus',
            old_name='api',
            new_name='gateway',
        ),
        migrations.RenameField(
            model_name='apppermissionrecord',
            old_name='api',
            new_name='gateway',
        ),
        migrations.RenameField(
            model_name='appresourcepermission',
            old_name='api',
            new_name='gateway',
        ),
        migrations.AlterField(
            model_name='appapipermission',
            name='gateway',
            field=models.ForeignKey(db_column='api_id', on_delete=django.db.models.deletion.CASCADE, to='core.gateway'),
        ),
        migrations.AlterField(
            model_name='apppermissionapply',
            name='gateway',
            field=models.ForeignKey(db_column='api_id', on_delete=django.db.models.deletion.CASCADE, to='core.gateway'),
        ),
        migrations.AlterField(
            model_name='apppermissionapplystatus',
            name='gateway',
            field=models.ForeignKey(blank=True, db_column='api_id', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.gateway'),
        ),
        migrations.AlterField(
            model_name='apppermissionrecord',
            name='gateway',
            field=models.ForeignKey(db_column='api_id', on_delete=django.db.models.deletion.CASCADE, to='core.gateway'),
        ),
        migrations.AlterField(
            model_name='appresourcepermission',
            name='gateway',
            field=models.ForeignKey(db_column='api_id', on_delete=django.db.models.deletion.CASCADE, to='core.gateway'),
        ),
        migrations.AlterUniqueTogether(
            name='appapipermission',
            unique_together={('bk_app_code', 'gateway')},
        ),
        migrations.AlterUniqueTogether(
            name='apppermissionapplystatus',
            unique_together={('bk_app_code', 'gateway', 'resource')},
        ),
        migrations.AlterUniqueTogether(
            name='appresourcepermission',
            unique_together={('bk_app_code', 'gateway', 'resource_id')},
        ),
    ]