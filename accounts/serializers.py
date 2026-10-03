"""Serializers for authentication and the current-user endpoint."""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import User


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds `role` to the JWT claims and echoes basic user info in the body."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "role": self.user.role,
        }
        return data


class MeSerializer(serializers.ModelSerializer):
    """Current user with role-appropriate profile data."""

    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "profile")

    def get_profile(self, obj):
        if obj.role == User.Role.ANALYST:
            profile = getattr(obj, "analyst_profile", None)
            if profile is None:
                return None
            return {
                "department": profile.department,
                "cases_reviewed_count": profile.cases_reviewed_count,
            }
        if obj.role == User.Role.BANK_ADMIN:
            profile = getattr(obj, "bank_admin_profile", None)
            if profile is None:
                return None
            return {
                "bank_name": profile.bank_name,
                "api_key_label": profile.api_key_label,
            }
        return None
