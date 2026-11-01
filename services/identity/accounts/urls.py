from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("users", views.UserViewSet, basename="user")
router.register("hospitals", views.HospitalViewSet, basename="hospital")

urlpatterns = [
    path("login/", views.LoginView.as_view()),
    path("me/", views.MeView.as_view()),
    path("public-key/", views.PublicKeyView.as_view()),
    path("internal/hospitals/", views.InternalHospitals.as_view()),
    path("internal/claims/", views.ClaimView.as_view()),
    path("internal/claims/confirm/", views.ClaimConfirmView.as_view()),
    path("internal/claims/release/", views.ClaimReleaseView.as_view()),
    path("", include(router.urls)),
]
