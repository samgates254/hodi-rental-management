from django.http import HttpResponseNotFound


def placeholder(request):
    return HttpResponseNotFound('Maintenance API is not implemented yet.')
