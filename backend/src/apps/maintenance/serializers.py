from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.leases.models import Lease
from apps.properties.models import Unit
from .models import MaintenanceIssue, MaintenanceIssueAttachment, MaintenanceIssueUpdate

MAX_ISSUE_ATTACHMENTS = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
IMAGE_TYPES = {
	'image/jpeg': {'jpg', 'jpeg'},
	'image/png': {'png'},
	'image/webp': {'webp'},
	'image/gif': {'gif'},
	'image/heic': {'heic'},
	'image/heif': {'heif'},
}
VIDEO_TYPES = {
	'video/mp4': {'mp4'},
	'video/webm': {'webm'},
	'video/quicktime': {'mov'},
	'video/3gpp': {'3gp'},
}


class MaintenanceIssueUpdateSerializer(serializers.ModelSerializer):
	author_name = serializers.SerializerMethodField()

	class Meta:
		model = MaintenanceIssueUpdate
		fields = ('id', 'note', 'status', 'author_name', 'created_at')
		read_only_fields = ('id', 'author_name', 'created_at')

	def get_author_name(self, update):
		return update.author.get_full_name() or update.author.get_username()


class MaintenanceIssueSerializer(serializers.ModelSerializer):
	updates = MaintenanceIssueUpdateSerializer(many=True, read_only=True)
	attachments = serializers.SerializerMethodField()
	tenant_name = serializers.CharField(source='tenant.full_name', read_only=True)
	unit_name = serializers.CharField(source='unit.name', read_only=True)
	property_name = serializers.CharField(source='unit.building.property.name', read_only=True)
	organization = serializers.IntegerField(source='tenant.organization_id', read_only=True)
	operational_request_id = serializers.IntegerField(read_only=True, allow_null=True)

	class Meta:
		model = MaintenanceIssue
		fields = (
			'id', 'organization', 'tenant', 'tenant_name', 'unit', 'unit_name',
			'property_name', 'operational_request_id', 'title',
			'category', 'priority', 'description', 'status', 'resolved_at',
			'created_at', 'updated_at', 'updates', 'attachments',
		)
		read_only_fields = fields

	def get_attachments(self, issue):
		request = self.context.get('request')
		return [
			{
				'id': attachment.pk,
				'url': request.build_absolute_uri(
					f'/api/v1/maintenance/issues/{issue.pk}/attachments/{attachment.pk}/',
				) if request else f'/api/v1/maintenance/issues/{issue.pk}/attachments/{attachment.pk}/',
				'file_name': attachment.file_name,
				'content_type': attachment.content_type,
				'media_type': attachment.media_type,
				'created_at': attachment.created_at,
			}
			for attachment in issue.attachments.all()
		]


class MaintenanceIssueCreateSerializer(serializers.ModelSerializer):
	unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(), required=False)
	attachments = serializers.ListField(
		child=serializers.FileField(),
		write_only=True,
		required=False,
		allow_empty=True,
	)

	class Meta:
		model = MaintenanceIssue
		fields = ('id', 'unit', 'title', 'category', 'priority', 'description', 'attachments')
		read_only_fields = ('id',)

	def validate_attachments(self, files):
		if len(files) > MAX_ISSUE_ATTACHMENTS:
			raise serializers.ValidationError(f'Attach no more than {MAX_ISSUE_ATTACHMENTS} photos or videos.')
		for uploaded in files:
			content_type = uploaded.content_type or ''
			extension = uploaded.name.rsplit('.', 1)[-1].lower() if '.' in uploaded.name else ''
			if content_type in IMAGE_TYPES and extension in IMAGE_TYPES[content_type]:
				max_bytes = MAX_IMAGE_BYTES
			elif content_type in VIDEO_TYPES and extension in VIDEO_TYPES[content_type]:
				max_bytes = MAX_VIDEO_BYTES
			else:
				raise serializers.ValidationError(
					'Attachments must be supported photo or video files (JPEG, PNG, WebP, GIF, HEIC, HEIF, MP4, WebM, MOV, or 3GP).',
				)
			if uploaded.size > max_bytes:
				limit_mb = max_bytes // (1024 * 1024)
				raise serializers.ValidationError(
					f'{uploaded.name} exceeds the {limit_mb} MB limit for this media type.',
				)
		return files

	def create(self, validated_data):
		attachments = validated_data.pop('attachments', [])
		issue = super().create(validated_data)
		for uploaded in attachments:
			content_type = uploaded.content_type
			media_type = (
				MaintenanceIssueAttachment.MediaType.IMAGE
				if content_type.startswith('image/')
				else MaintenanceIssueAttachment.MediaType.VIDEO
			)
			MaintenanceIssueAttachment.objects.create(
				issue=issue,
				file=uploaded,
				file_name=uploaded.name[:255],
				content_type=content_type,
				media_type=media_type,
			)
		return issue

	def validate_unit(self, unit):
		tenant = self.context['tenant']
		if unit.organization_id != tenant.organization_id:
			raise serializers.ValidationError('The unit must belong to your organization.')
		today = timezone.localdate()
		if not Lease.objects.filter(
			tenant=tenant,
			unit=unit,
			status=Lease.Status.ACTIVE,
			start_date__lte=today,
		).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).exists():
			raise serializers.ValidationError('The unit must be linked to your active lease.')
		return unit
