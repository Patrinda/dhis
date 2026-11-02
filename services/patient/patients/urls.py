from django.urls import path

from . import views

urlpatterns = [
    path("", views.PatientList.as_view()),
    path("lookup/", views.LookupView.as_view()),
    path("<uuid:pk>/", views.PatientDetail.as_view()),
]

internal_urlpatterns = [
    path("exists/", views.InternalExists.as_view()),
    path("by-national-id/", views.InternalByNationalId.as_view()),
    path("by-id/<uuid:pk>/", views.InternalById.as_view()),
]
