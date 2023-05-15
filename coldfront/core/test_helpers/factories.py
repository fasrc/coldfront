from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

from factory import SubFactory
from faker import Faker
from faker.providers import BaseProvider, DynamicProvider
from factory.django import DjangoModelFactory

from coldfront.core.field_of_science.models import FieldOfScience
from coldfront.core.resource.models import ResourceType, Resource
# from coldfront.core.department.models import Department
from coldfront.core.project.models import (Project,
                                            ProjectUser,
                                            ProjectAttribute,
                                            ProjectAttributeType,
                                            ProjectUserRoleChoice,
                                            ProjectUserStatusChoice,
                                            ProjectStatusChoice,
                                            AttributeType as PAttributeType,
                                        )
from coldfront.core.allocation.models import (Allocation,
                                            AllocationUser,
                                            AllocationUserNote,
                                            AllocationStatusChoice,
                                            AllocationUserStatusChoice,
                                        )
from coldfront.core.grant.models import GrantFundingAgency, GrantStatusChoice
from coldfront.core.publication.models import PublicationSource



fake = Faker()

class ColdfrontProvider(BaseProvider):
    def project_title(self):
        return f'{fake.last_name()}_lab'.lower()

    def resource_name(self):
        return fake.word().lower()+ '/' + fake.word().lower()

    def username(self):
        first_name = fake.first_name()
        last_name = fake.last_name()
        return f'{first_name}{last_name}'.lower()

field_of_science_provider = DynamicProvider(
     provider_name="fieldofscience",
     elements=['Chemistry', 'Physics', 'Economics', 'Biology', 'Statistics', 'Astrophysics'],
)

fake.add_provider(ColdfrontProvider)
fake.add_provider(field_of_science_provider)


### User factories ###

class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ('username',)
    username = fake.unique.username()
    email = username + '@example.com'
    is_staff = False
    is_active = True
    is_superuser = False




### Allocation factories ###


class AllocationStatusChoiceFactory(DjangoModelFactory):
    class Meta:
        model = AllocationStatusChoice
        django_get_or_create = ('name',)
    name = 'Active'


class AllocationFactory(DjangoModelFactory):
    class Meta:
        model = Allocation
        django_get_or_create = ('project','resource')
    justification = fake.sentence()
    status = AllocationStatusChoiceFactory()


class AllocationUserStatusChoiceFactory(DjangoModelFactory):
    class Meta:
        model = AllocationUserStatusChoice
        django_get_or_create = ('name',)
    name = 'Active'


class AllocationUserFactory(DjangoModelFactory):
    class Meta:
        model = AllocationUser
        django_get_or_create = ('allocation','user')
    allocation = SubFactory(AllocationFactory)
    user = SubFactory(UserFactory)
    status = AllocationUserStatusChoiceFactory()
    unit = 'GB'
    usage = 100
    usage_bytes = 100000000000


class AllocationUserNoteFactory(DjangoModelFactory):
    class Meta:
        model = AllocationUserNote
        django_get_or_create = ('allocation')
    allocation = SubFactory(AllocationFactory)
    author = SubFactory(AllocationUserFactory)
    note = fake.sentence()




### Field of Science factories ###

class FieldOfScienceFactory(DjangoModelFactory):
    class Meta:
        model = FieldOfScience
        django_get_or_create = ('description',)

    description = fake.fieldofscience()





### Department factories ###

# class DepartmentFactory(DjangoModelFactory):
#     class Meta:
#         model = Department




### Grant factories ###

class GrantFundingAgencyFactory(DjangoModelFactory):
    class Meta:
        model = GrantFundingAgency


class GrantStatusChoiceFactory(DjangoModelFactory):
    class Meta:
        model = GrantStatusChoice


### Project factories ###

class ProjectStatusChoiceFactory(DjangoModelFactory):
    class Meta:
        model = ProjectStatusChoice
        django_get_or_create = ('name',)
    name = 'Active'


class ProjectFactory(DjangoModelFactory):
    class Meta:
        model = Project
        django_get_or_create = ('title',)

    title = fake.unique.project_title()
    pi = SubFactory(UserFactory)
    description = fake.sentence()
    field_of_science = SubFactory(FieldOfScienceFactory)
    status = SubFactory(ProjectStatusChoiceFactory)
    force_review = False
    requires_review = False
    # force_review = fake.boolean()
    # requires_review = fake.boolean()

class ProjectUserRoleChoiceFactory(DjangoModelFactory):
    class Meta:
        model = ProjectUserRoleChoice
        django_get_or_create = ('name',)
    name = 'User'

class ProjectUserStatusChoiceFactory(DjangoModelFactory):
    class Meta:
        model = ProjectUserStatusChoice
        django_get_or_create = ('name',)
    name = 'Active'

class ProjectUserFactory(DjangoModelFactory):
    class Meta:
        model = ProjectUser

    project = SubFactory(ProjectFactory)
    user = SubFactory(UserFactory)
    role = SubFactory(ProjectUserRoleChoiceFactory)
    status = SubFactory(ProjectUserStatusChoiceFactory)



### Project Attribute factories ###

class PAttributeTypeFactory(DjangoModelFactory):
    class Meta:
        model = PAttributeType
        # django_get_or_create = ('name',)
    name='Text'

class ProjectAttributeTypeFactory(DjangoModelFactory):
    class Meta:
        model = ProjectAttributeType
    name = 'Test attribute type'
    attribute_type = SubFactory(PAttributeTypeFactory)


class ProjectAttributeFactory(DjangoModelFactory):
    class Meta:
        model = ProjectAttribute
    proj_attr_type = SubFactory(ProjectAttributeTypeFactory)
    value = 'Test attribute value'
    project = SubFactory(ProjectFactory)




### Publication factories ###
class PublicationSourceFactory(DjangoModelFactory):
    class Meta:
        model = PublicationSource

    name = 'doi'
    url = 'https://doi.org/'


### Resource factories ###

class ResourceFactory(DjangoModelFactory):
    class Meta:
        model = Resource
        django_get_or_create = ('name',)
    name = fake.unique.resource_name()
    description = fake.sentence()


class ResourceTypeFactory(DjangoModelFactory):
    class Meta:
        model = ResourceType
