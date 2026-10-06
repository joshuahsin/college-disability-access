from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    CampusViewSet,
    CommentReactionViewSet,
    CommentViewSet,
    ConfirmationViewSet,
    FeatureViewSet,
    RegisterView,
    SubmissionViewSet,
    VenueViewSet,
)

router = DefaultRouter()
router.register("campuses", CampusViewSet, basename="campus")
router.register("venues", VenueViewSet, basename="venue")
router.register("features", FeatureViewSet, basename="feature")
router.register("submissions", SubmissionViewSet, basename="submission")
router.register("confirmations", ConfirmationViewSet, basename="confirmation")
router.register("comments", CommentViewSet, basename="comment")
router.register("comment-reactions", CommentReactionViewSet, basename="comment-reaction")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("", include(router.urls)),
]
