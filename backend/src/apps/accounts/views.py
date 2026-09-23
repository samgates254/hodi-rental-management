from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.response import Response
from rest_framework.views import APIView


class LoginView(ObtainAuthToken):
	"""Exchange username and password for an API token."""


class LogoutView(APIView):
	permission_classes = (permissions.IsAuthenticated,)

	def post(self, request):
		Token.objects.filter(user=request.user).delete()
		return Response(status=status.HTTP_204_NO_CONTENT)
