"""django-filter FilterSet for the analyst queue."""
import django_filters

from incidents.models import Incident


class IncidentFilter(django_filters.FilterSet):
    # Filter by platform code (instagram/tiktok/youtube).
    platform = django_filters.CharFilter(field_name="video__platform__code")
    risk_score_min = django_filters.NumberFilter(
        field_name="risk_score", lookup_expr="gte"
    )
    risk_score_max = django_filters.NumberFilter(
        field_name="risk_score", lookup_expr="lte"
    )
    date_from = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    date_to = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    class Meta:
        model = Incident
        # `status` is a model field → exact-match filter generated automatically.
        fields = ["status", "platform", "risk_score_min", "risk_score_max",
                  "date_from", "date_to"]
