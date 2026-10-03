from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from ingestion.models import Video

class ScreeningResultView(APIView):
    """
    GET /api/screening/{video_id}/result/
    Returns the Stage 1 ScreeningResult with all signals.
    """
    def get(self, request, video_id):
        video = get_object_or_404(Video, id=video_id)
        
        if not hasattr(video, 'screening_result'):
            return Response({"error": "No screening result found for this video."}, status=status.HTTP_404_NOT_FOUND)
            
        result = video.screening_result
        signals = result.signals.all()
        
        data = {
            "id": result.id,
            "status": result.status,
            "processing_time_ms": result.processing_time_ms,
            "triggered_at": result.triggered_at,
            "signals": [
                {
                    "module": sig.module,
                    "is_triggered": sig.is_triggered,
                    "confidence": sig.confidence,
                    "raw_output": sig.raw_output
                } for sig in signals
            ]
        }
        
        return Response(data)
