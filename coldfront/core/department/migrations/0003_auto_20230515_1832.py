# Generated by Django 3.2.17 on 2023-05-15 22:32

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ifx', '0005_auto_20211003_1153'),
        ('ifxuser', '0014_auto_20221220_1921'),
        ('department', '0002_auto_20220830_1537'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepartmentAdminNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('note', models.TextField()),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='DepartmentUserNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('is_private', models.BooleanField(default=True)),
                ('note', models.TextField()),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RemoveField(
            model_name='departmentmember',
            name='department',
        ),
        migrations.RemoveField(
            model_name='departmentmember',
            name='member',
        ),
        migrations.RemoveField(
            model_name='departmentmember',
            name='role',
        ),
        migrations.RemoveField(
            model_name='departmentmember',
            name='status',
        ),
        migrations.RemoveField(
            model_name='departmentproject',
            name='department',
        ),
        migrations.RemoveField(
            model_name='departmentproject',
            name='project',
        ),
        migrations.RemoveField(
            model_name='historicaldepartment',
            name='history_user',
        ),
        migrations.RemoveField(
            model_name='historicaldepartment',
            name='parent',
        ),
        migrations.RemoveField(
            model_name='historicaldepartment',
            name='rank',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentmember',
            name='department',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentmember',
            name='history_user',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentmember',
            name='member',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentmember',
            name='role',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentmember',
            name='status',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentproject',
            name='department',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentproject',
            name='history_user',
        ),
        migrations.RemoveField(
            model_name='historicaldepartmentproject',
            name='project',
        ),
        migrations.DeleteModel(
            name='Department',
        ),
        migrations.DeleteModel(
            name='DepartmentMember',
        ),
        migrations.DeleteModel(
            name='DepartmentMemberRole',
        ),
        migrations.DeleteModel(
            name='DepartmentMemberStatus',
        ),
        migrations.DeleteModel(
            name='DepartmentProject',
        ),
        migrations.DeleteModel(
            name='DepartmentRank',
        ),
        migrations.DeleteModel(
            name='HistoricalDepartment',
        ),
        migrations.DeleteModel(
            name='HistoricalDepartmentMember',
        ),
        migrations.DeleteModel(
            name='HistoricalDepartmentProject',
        ),
        migrations.CreateModel(
            name='Department',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('ifxuser.organization',),
        ),
        migrations.CreateModel(
            name='DepartmentMember',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('ifxuser.useraffiliation',),
        ),
        migrations.CreateModel(
            name='DepartmentProject',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('ifx.projectorganization',),
        ),
        migrations.AddField(
            model_name='departmentusernote',
            name='department',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='department.department'),
        ),
        migrations.AddField(
            model_name='departmentadminnote',
            name='department',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='department.department'),
        ),
    ]
