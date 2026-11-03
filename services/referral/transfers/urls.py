from django.urls import path

from . import views

urlpatterns = [
    path("", views.TransferList.as_view()),
    path("run-expiry/", views.RunExpiry.as_view()),
    path("<uuid:pk>/", views.TransferDetail.as_view()),
    path("<uuid:pk>/<slug:action>/", views.TransferAction.as_view()),
]
