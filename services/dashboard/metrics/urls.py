from django.urls import path

from . import views

urlpatterns = [
    path("summary/", views.Summary.as_view()),
    path("timeseries/", views.Timeseries.as_view()),
    path("conditions/", views.Conditions.as_view()),
    path("hospitals/", views.Hospitals.as_view()),
    path("transfers/", views.RecentTransfers.as_view()),
]
