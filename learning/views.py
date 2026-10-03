from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from core.permissions import IsAfmLeadOrAbove, IsAnalystOrAbove
from learning.models import KeywordDictionaryEntry, KeywordDictionaryVersion, FineTuningRun
from learning.services import approve_or_reject_dictionary_entry, rollback_dictionary_version
from learning.training import (
    feature_importances,
    get_active_model_run,
    predict_incident_risk,
    train_risk_model,
)

class DictionaryReviewView(APIView):
    permission_classes = [IsAfmLeadOrAbove]
    
    def post(self, request, entry_id):
        decision = request.data.get("decision")
        if decision not in ["approve", "reject"]:
            return Response({"error": "Decision must be 'approve' or 'reject'"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            version = approve_or_reject_dictionary_entry(entry_id, decision)
            return Response({"message": f"Entry {decision}d", "new_version_id": version.id})
        except KeywordDictionaryEntry.DoesNotExist:
            return Response({"error": "Entry not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DictionaryRollbackView(APIView):
    permission_classes = [IsAfmLeadOrAbove]
    
    def post(self, request, version_id):
        try:
            version = rollback_dictionary_version(version_id)
            return Response({"message": f"Rolled back to version {version_id}", "new_version_id": version.id})
        except KeywordDictionaryVersion.DoesNotExist:
            return Response({"error": "Version not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PendingDictionaryEntriesView(APIView):
    """List dictionary entries awaiting review (for the leadership UI, G7)."""
    permission_classes = [IsAfmLeadOrAbove]

    def get(self, request):
        entries = KeywordDictionaryEntry.objects.filter(
            status=KeywordDictionaryEntry.Status.PENDING_REVIEW
        ).order_by("-added_at")
        data = [
            {
                "id": e.id,
                "term": e.term,
                "category": e.category,
                "added_automatically": e.added_automatically,
                "confirmation_count": e.confirmation_count,
                "added_at": e.added_at,
            }
            for e in entries
        ]
        return Response(data)


class DictionaryVersionListView(APIView):
    """List dictionary versions (history) with their snapshots (G7)."""
    permission_classes = [IsAfmLeadOrAbove]

    def get(self, request):
        versions = KeywordDictionaryVersion.objects.all().order_by("-created_at")
        data = [
            {
                "id": v.id,
                "note": v.note,
                "created_at": v.created_at,
                "term_count": len(v.snapshot or []),
                "snapshot": v.snapshot,
            }
            for v in versions
        ]
        return Response(data)


class FineTuningRunListView(APIView):
    permission_classes = [IsAfmLeadOrAbove]

    def get(self, request):
        runs = FineTuningRun.objects.all().order_by('-created_at')
        data = [
            {
                "id": run.id,
                "status": run.status,
                "is_active": run.is_active,
                "training_examples_count": run.training_examples_count,
                "precision": run.precision,
                "recall": run.recall,
                "false_positive_rate": run.false_positive_rate,
                "notes": run.notes,
                "created_at": run.created_at,
                "completed_at": run.completed_at,
            }
            for run in runs
        ]
        return Response(data)


class TrainRiskModelView(APIView):
    """POST /api/learning/model/train/ — run a synchronous training cycle."""
    permission_classes = [IsAfmLeadOrAbove]

    def post(self, request):
        try:
            min_examples = int(request.data.get("min_examples", 10))
        except (TypeError, ValueError):
            return Response({"error": "min_examples must be an integer."},
                            status=status.HTTP_400_BAD_REQUEST)
        run = train_risk_model(min_examples=min_examples)
        return Response({
            "run_id": run.id,
            "status": run.status,
            "is_active": run.is_active,
            "training_examples_count": run.training_examples_count,
            "precision": run.precision,
            "recall": run.recall,
            "false_positive_rate": run.false_positive_rate,
            "notes": run.notes,
        })


class ActiveRiskModelView(APIView):
    """GET /api/learning/model/active/ — deployed model metrics + feature weights."""
    permission_classes = [IsAfmLeadOrAbove]

    def get(self, request):
        run = get_active_model_run()
        if run is None:
            return Response({"detail": "No risk model has been trained and deployed yet."},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({
            "run_id": run.id,
            "status": run.status,
            "training_examples_count": run.training_examples_count,
            "precision": run.precision,
            "recall": run.recall,
            "false_positive_rate": run.false_positive_rate,
            "deployed_at": run.completed_at,
            "feature_importances": feature_importances(run),
        })


class PredictIncidentRiskView(APIView):
    """GET /api/learning/model/predict/<id>/ — ML risk for one incident."""
    permission_classes = [IsAnalystOrAbove]

    def get(self, request, incident_id):
        from incidents.models import Incident

        try:
            incident = Incident.objects.select_related(
                "video", "video__social_account", "deep_analysis_result"
            ).get(id=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident not found"}, status=status.HTTP_404_NOT_FOUND)

        prediction = predict_incident_risk(incident)
        if prediction is None:
            return Response({"detail": "No risk model has been trained and deployed yet."},
                            status=status.HTTP_404_NOT_FOUND)
        prediction["incident_id"] = incident.id
        prediction["rule_based_risk_score"] = incident.risk_score
        return Response(prediction)
