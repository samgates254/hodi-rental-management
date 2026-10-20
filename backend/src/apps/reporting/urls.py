from django.urls import path

from .views import ChargeJournalReportView


app_name = 'reporting'

urlpatterns = [
    path(
        'charge-journal/',
        ChargeJournalReportView.as_view(),
        name='charge-journal',
    ),
]
