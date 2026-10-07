from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .statements import build_statement, statement_pdf


class MyStatementView(APIView):
	"""Statement for the authenticated user's own tenant record. Client tenant ids are ignored."""

	permission_classes = (IsAuthenticated,)

	def get(self, request):
		return Response(build_statement(request.user, request.query_params))


class MyStatementPdfView(APIView):
	permission_classes = (IsAuthenticated,)

	def get(self, request):
		statement = build_statement(request.user, request.query_params)
		period = statement['period']
		filename = f"hodi-statement-{period['start']}-to-{period['end']}.pdf"
		response = HttpResponse(statement_pdf(statement), content_type='application/pdf')
		response['Content-Disposition'] = f'attachment; filename="{filename}"'
		response['X-Content-Type-Options'] = 'nosniff'
		response['Cache-Control'] = 'private, no-store'
		return response
