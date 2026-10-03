"""Serializers for deep-analysis outputs (reasoning graph)."""
from rest_framework import serializers

from deepanalysis.services import get_reasoning_graph


class ReasoningGraphSerializer(serializers.Serializer):
    """Shapes an Incident into the vis-network graph structure.

    The actual {nodes, edges, verdict} assembly (incl. the explicit-vs-fallback
    decision) lives in `deepanalysis.services.get_reasoning_graph`.
    """

    def to_representation(self, incident):
        return get_reasoning_graph(incident)
