from django.urls import path

from apps.accounts.views import (
    ChangePasswordView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    ResetPasswordConfirmView,
)
from apps.accounts.views_registration import (
    EmailVerificationConfirmView,
    EmailVerificationResendView,
    MemberSignUpView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="auth-me"),
    path("change-password", ChangePasswordView.as_view(), name="auth-change-password"),
    path("forgot-password", ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("reset-password", ResetPasswordConfirmView.as_view(), name="auth-reset-password"),
    path("member-sign-up", MemberSignUpView.as_view(), name="auth-member-sign-up"),
    path("email-verification/resend", EmailVerificationResendView.as_view(), name="auth-email-verification-resend"),
    path("email-verification/confirm", EmailVerificationConfirmView.as_view(), name="auth-email-verification-confirm"),
]
