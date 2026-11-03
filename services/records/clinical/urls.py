from django.urls import path

from . import views

urlpatterns = [
    path("encounters/", views.EncounterList.as_view()),
    path("encounters/<uuid:pk>/", views.EncounterDetail.as_view()),
    path("allergies/", views.AllergyList.as_view()),
    path("prescriptions/", views.PrescriptionList.as_view()),
    path("prescriptions/<uuid:pk>/dispense/", views.PrescriptionDispense.as_view()),
    path("lab-orders/", views.LabOrderList.as_view()),
    path("lab-orders/<uuid:pk>/result/", views.LabOrderResult.as_view()),
    path("break-glass/", views.BreakGlass.as_view()),
]

internal_urlpatterns = [
    path("summary/", views.InternalSummary.as_view()),
]
