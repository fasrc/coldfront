from django.db import models
from django.conf import settings

from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

from coldfront.core.project.models import Project
from coldfront.core.field_of_science.models import FieldOfScience


class DepartmentRank(TimeStampedModel):
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Department(TimeStampedModel):
    """
    Consists of all entities in nanites_organization where rank != lab. If is_biller
    is True, Coldfront will generate invoices for the Department.
    """
    name = models.CharField(max_length=255,)
    rank = models.ForeignKey(DepartmentRank, on_delete=models.CASCADE)
    projects = models.ManyToManyField(Project, through='DepartmentProjects')
    # field_of_science = models.ForeignKey(FieldOfScience, on_delete=models.CASCADE,
    #                                             default=FieldOfScience.DEFAULT_PK)
    history = HistoricalRecords()


class DepartmentProjects(TimeStampedModel):
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    dept_billing = models.BooleanField(default=False)


class DepartmentMemberRole(TimeStampedModel):
    """
    """
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class DepartmentMemberStatus(TimeStampedModel):
    """
    """
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']



class DepartmentMember(TimeStampedModel):
    """
    """
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    role = models.ForeignKey(DepartmentMemberRole, on_delete=models.CASCADE)
    status = models.ForeignKey(DepartmentMemberStatus, on_delete=models.CASCADE)
    enable_notifications = models.BooleanField(default=True)
    history = HistoricalRecords()