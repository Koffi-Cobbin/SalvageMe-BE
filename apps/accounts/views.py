from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginRequestSerializer, RegisterSerializer, SetPasswordSerializer, UserMeSerializer


def generate_password_set_link(user) -> tuple[str, str]:
    """
    Returns (uid, token) for a password-set/invite link — standard Django
    idiom, reusing what's already in the framework. Used both by the
    (currently absent) generic invite path and, in the near future, by
    apps/partners — see that app's services.py for the actual email send.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return uid, token


def _set_refresh_cookie(response, refresh_token: str):
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=str(refresh_token),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path=settings.REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response):
    response.delete_cookie(key=settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        response = Response(
            {"access": str(refresh.access_token), "user": UserMeSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )
        _set_refresh_cookie(response, refresh)
        return response


class LoginView(APIView):
    serializer_class = LoginRequestSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = TokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tokens = serializer.validated_data
        user = serializer.user

        response = Response(
            {"access": str(tokens["access"]), "user": UserMeSerializer(user).data},
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, tokens["refresh"])
        return response


class RefreshView(APIView):
    """
    Reads the refresh token from the httpOnly cookie (never the request
    body) and issues a fresh access token, rotating the refresh cookie.
    """

    serializer_class = None
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw_token = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw_token:
            return Response({"detail": "No refresh cookie present."}, status=status.HTTP_401_UNAUTHORIZED)

        from django.contrib.auth import get_user_model

        try:
            refresh = RefreshToken(raw_token)
            access = refresh.access_token
            new_refresh = refresh

            if settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS"):
                User = get_user_model()
                user = User.objects.get(pk=refresh["user_id"])
                new_refresh = RefreshToken.for_user(user)
                if settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION"):
                    try:
                        refresh.blacklist()
                    except AttributeError:
                        pass
        except TokenError:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({"access": str(access)}, status=status.HTTP_200_OK)
        if new_refresh is not refresh:
            _set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    serializer_class = None
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw_token = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw_token:
            try:
                RefreshToken(raw_token).blacklist()
            except TokenError:
                pass  # already invalid/expired — logout should still succeed

        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class UserMeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserMeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class SetPasswordView(APIView):
    """
    POST /auth/set-password/ — the counterpart to generate_password_set_link().
    Public (the token itself is the auth). Used both for accounts created
    with an unusable password (e.g. apps/partners) and, in the future, a
    general "forgot password" flow reusing this same endpoint.
    """

    serializer_class = SetPasswordSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        User = get_user_model()
        try:
            uid = urlsafe_base64_decode(serializer.validated_data["uid"]).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"detail": "Invalid link.", "code": "invalid_token"}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, serializer.validated_data["token"]):
            return Response(
                {"detail": "This link is invalid or has expired.", "code": "invalid_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.is_verified = True
        user.save(update_fields=["password", "is_verified"])

        # If this is completing a partner application's verification step,
        # finish it here rather than making the frontend orchestrate two
        # calls — see apps/partners/services.py.
        from apps.partners.services import complete_email_verification_if_pending

        complete_email_verification_if_pending(user)

        return Response(status=status.HTTP_204_NO_CONTENT)
