from django.http import HttpResponseNotFound


def placeholder(request):
    return HttpResponseNotFound('Notifications API is not implemented yet.')
