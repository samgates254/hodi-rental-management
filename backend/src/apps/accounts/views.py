from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import OrganizationMembership


class LoginView(ObtainAuthToken):
	"""Exchange username and password for an API token."""

	def post(self, request, *args, **kwargs):
		response = super().post(request, *args, **kwargs)
		user_id = Token.objects.only('user_id').get(key=response.data['token']).user_id
		memberships = OrganizationMembership.objects.filter(
			user_id=user_id,
			is_active=True,
			organization__is_active=True,
		).select_related('organization').order_by('organization__name')
		response.data['memberships'] = [
			{
				'organization_id': membership.organization_id,
				'organization_name': membership.organization.name,
				'role': membership.role,
			}
			for membership in memberships
		]
		return response


class LogoutView(APIView):
	permission_classes = (permissions.IsAuthenticated,)

	def post(self, request):
		Token.objects.filter(user=request.user).delete()
		return Response(status=status.HTTP_204_NO_CONTENT)
