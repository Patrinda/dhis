from django.urls import path

from . import views

urlpatterns = [
    path("", views.AuditList.as_view()),
    path("verify/", views.AuditVerify.as_view()),
    path("<int:seq>/review/", views.BreakGlassReviewView.as_view()),
]

consent_urlpatterns = [
    path("", views.ConsentList.as_view()),
    path("withdraw/", views.ConsentWithdraw.as_view()),
    path("status/", views.ConsentStatus.as_view()),
]

internal_urlpatterns = [
    path("consents/check/", views.ConsentCheck.as_view()),
]
