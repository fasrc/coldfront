from datetime import timedelta

from django.contrib.auth import get_user_model
from ifxuser.models import Organization, UserAffiliation
from rest_framework import serializers

from coldfront.core.resource.models import Resource
from coldfront.core.project.models import Project, ProjectUser
from coldfront.core.allocation.models import Allocation, AllocationAttribute, AllocationChangeRequest, AllocationUser
from coldfront.plugins.ifx.models import ProjectOrganization


class UserAffiliationSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field='ifxorg', read_only=True)

    class Meta:
        model = UserAffiliation
        fields = (
            'organization',
            'role',
            'active',
        )


class OrganizationSerializer(serializers.ModelSerializer):
    project = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = (
            'ifxorg',
            'name',
            'rank',
            'org_tree',
            'project'
        )


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = get_user_model()
        fields = (
            'id',
            'username',
            'full_name',
            'is_active',
            'is_superuser',
            'is_staff',
            'date_joined',
            'last_update',
        )


class ResourceSerializer(serializers.ModelSerializer):
    resource_type = serializers.SlugRelatedField(slug_field='name', read_only=True)

    class Meta:
        model = Resource
        fields = ('id', 'resource_type', 'name', 'description', 'is_allocatable')


class AllocationPctUsageField(serializers.Field):
    def to_representation(self, data):
        if data.usage and float(data.size):
            return round((data.usage / float(data.size) * 100), 2)
        if data.usage == 0:
            return 0
        return None


class AllocationSerializer(serializers.ModelSerializer):
    resource = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    project = serializers.SlugRelatedField(slug_field='title', read_only=True)
    status = serializers.SlugRelatedField(slug_field='name', read_only=True)
    size = serializers.FloatField()
    pct_full = AllocationPctUsageField(source='*')

    class Meta:
        model = Allocation
        fields = (
            'id',
            'project',
            'resource',
            'status',
            'path',
            'size',
            'usage',
            'pct_full',
            'cost',
            'created',
        )

    def get_resource(self, obj):
        # Equivalent to Allocation.get_resources_as_string, but reads obj.resources.all()
        # with no further chaining so it can reuse the view's prefetch cache (which
        # already applies the same ordering) instead of re-querying per row.
        return ', '.join(resource.name for resource in obj.resources.all())

    def get_path(self, obj):
        # Equivalent to Allocation.path, but reads from the prefetched
        # allocationattribute_set instead of querying AllocationAttributeType and
        # AllocationAttribute fresh for every row.
        for attribute in obj.allocationattribute_set.all():
            if attribute.allocation_attribute_type.name == 'Subdirectory':
                return attribute.value
        return ''

    def get_type(self, obj):
        resource = obj.get_parent_resource
        if resource:
            return resource.resource_type.name
        return None


class AllocationAttributeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='allocation_attribute_type.name', read_only=True)
    usage = serializers.SerializerMethodField()

    class Meta:
        model = AllocationAttribute
        fields = ('name', 'value', 'usage')

    def get_usage(self, obj):
        usage = getattr(obj, 'allocationattributeusage', None)
        return usage.value if usage else None


class AllocationUserUsageSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    status = serializers.SlugRelatedField(slug_field='name', read_only=True)

    class Meta:
        model = AllocationUser
        fields = ('username', 'status', 'usage', 'usage_bytes', 'unit')


class AllocationBillingDetailSerializer(AllocationSerializer):
    '''AllocationSerializer plus the allocation's full attribute list and per-user
    usage, for troubleshooting bills on a specific allocation.
    '''
    attributes = AllocationAttributeSerializer(source='allocationattribute_set', many=True, read_only=True)
    users = AllocationUserUsageSerializer(source='allocationuser_set', many=True, read_only=True)

    class Meta(AllocationSerializer.Meta):
        fields = AllocationSerializer.Meta.fields + ('attributes', 'users')


class AllocationRequestSerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(slug_field='title', read_only=True)
    pi = serializers.ReadOnlyField(source='project.pi.full_name')
    resource = serializers.ReadOnlyField(source='get_parent_resource.name', allow_null=True)
    tier = serializers.ReadOnlyField(source='get_parent_resource.parent_resource.name', allow_null=True)
    status = serializers.SlugRelatedField(slug_field='name', read_only=True)
    requested_size = serializers.ReadOnlyField(source='quantity')
    current_size = serializers.ReadOnlyField(source='size')
    created = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    created_by = serializers.SerializerMethodField(read_only=True)
    fulfilled_date = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    fulfilled_by = serializers.SerializerMethodField(read_only=True)
    time_to_fulfillment = serializers.DurationField(read_only=True)

    class Meta:
        model = Allocation
        fields = (
            'id',
            'project',
            'pi',
            'resource',
            'tier',
            'path',
            'status',
            'requested_size',
            'current_size',
            'created',
            'created_by',
            'fulfilled_date',
            'fulfilled_by',
            'time_to_fulfillment',
        )

    def get_created_by(self, obj):
        historical_record = obj.history.earliest()
        creator = historical_record.history_user if historical_record else None
        if not creator:
            return None
        return historical_record.history_user.username

    def get_fulfilled_by(self, obj):
        historical_records = obj.history.filter(status__name='Active')
        if historical_records:
            user = historical_records.earliest().history_user
            if user:
                return user.username
        return None


class AllocationChangeRequestSerializer(serializers.ModelSerializer):
    project = serializers.ReadOnlyField(source='allocation.project.title')
    pi = serializers.ReadOnlyField(source='allocation.project.pi.full_name')
    resource = serializers.ReadOnlyField(source='allocation.get_resources_as_string')
    tier = serializers.ReadOnlyField(source='allocation.get_parent_resource.parent_resource.name', allow_null=True)
    status = serializers.SlugRelatedField(slug_field='name', read_only=True)
    created = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    created_by = serializers.SerializerMethodField(read_only=True)
    fulfilled_date = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    fulfilled_by = serializers.SerializerMethodField(read_only=True)
    time_to_fulfillment = serializers.DurationField(read_only=True)

    class Meta:
        model = AllocationChangeRequest
        fields = (
            'id',
            'allocation',
            'project',
            'pi',
            'resource',
            'tier',
            'justification',
            'status',
            'created',
            'created_by',
            'fulfilled_date',
            'fulfilled_by',
            'time_to_fulfillment',
        )

    def get_created_by(self, obj):
        historical_record = obj.history.earliest()
        creator = historical_record.history_user if historical_record else None
        if not creator:
            return None
        return historical_record.history_user.username

    def get_fulfilled_by(self, obj):
        if not obj.status.name == 'Approved':
            return None
        historical_record = obj.history.latest()
        fulfiller = historical_record.history_user if historical_record else None
        if not fulfiller:
            return None
        return historical_record.history_user.username


class ProjAllocationSerializer(serializers.ModelSerializer):
    resource = serializers.ReadOnlyField(source='get_resources_as_string')
    status = serializers.SlugRelatedField(slug_field='name', read_only=True)
    size = serializers.FloatField()

    class Meta:
        model = Allocation
        fields = ('id', 'resource', 'status', 'path', 'size', 'usage')


class ProjectUserSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(slug_field='username', read_only=True)
    status = serializers.SlugRelatedField(slug_field='name', read_only=True)
    role = serializers.SlugRelatedField(slug_field='name', read_only=True)

    class Meta:
        model = ProjectUser
        fields = ('user', 'role', 'status')


class ProjectSerializer(serializers.ModelSerializer):
    pi = serializers.SlugRelatedField(slug_field='full_name', read_only=True)
    status = serializers.SlugRelatedField(slug_field='name', read_only=True)
    project_users = serializers.SerializerMethodField()
    allocations = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id',
            'title',
            'pi',
            'status',
            'project_users',
            'allocations',
            'created',
        )

    def get_project_users(self, obj):
        request = self.context.get('request', None)
        if request and request.query_params.get('project_users') in ['true','True']:
            return ProjectUserSerializer(obj.projectuser_set, many=True, read_only=True).data
        return None

    def get_allocations(self, obj):
        request = self.context.get('request', None)
        if request and request.query_params.get('allocations') in ['true','True']:
            return ProjAllocationSerializer(obj.allocation_set, many=True, read_only=True).data
        return None


class UnusedStorageAllocationSerializer(serializers.ModelSerializer):
    project = serializers.CharField(source='project.title', read_only=True)
    path = serializers.CharField(read_only=True)
    resource = serializers.ReadOnlyField(source='get_parent_resource.name', allow_null=True)
    pi = serializers.ReadOnlyField(source='project.pi.full_name')
    size_tb = serializers.FloatField(read_only=True, source='size')
    usage_bytes = serializers.SerializerMethodField()
    created = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = Allocation
        fields = (
            'id',
            'project',
            'resource',
            'path',
            'pi',
            'size_tb',
            'usage_bytes',
            'created',
        )

    def get_usage_bytes(self, obj):
        usage = obj.usage_exact if obj.usage_exact is not None else obj.usage
        return int(usage) if usage is not None else 0
