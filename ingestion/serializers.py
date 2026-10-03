"""Serializers for the ingestion API."""
from rest_framework import serializers

from ingestion.models import Video


class VideoSubmitSerializer(serializers.Serializer):
    """Request body for submitting a video URL for download."""

    url = serializers.URLField(max_length=500)


class VideoStatusSerializer(serializers.ModelSerializer):
    """Polling response for a video's collection status."""

    video_id = serializers.IntegerField(source="id", read_only=True)

    class Meta:
        model = Video
        # screening_status is added in the next prompt.
        fields = ("video_id", "download_status")
