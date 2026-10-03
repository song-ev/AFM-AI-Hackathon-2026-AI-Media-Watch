"""Request/response serializers for the bank API."""
from rest_framework import serializers


class RiskCheckRequestSerializer(serializers.Serializer):
    """Validates the risk-check request body."""

    account_identifier = serializers.CharField(max_length=128)
    identifier_type = serializers.ChoiceField(
        choices=["phone", "account_number", "social_handle"]
    )
