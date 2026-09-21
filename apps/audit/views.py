from django.http import HttpResponseNotFound


def placeholder(request):
    return HttpResponseNotFound('Audit API is not implemented yet.')
