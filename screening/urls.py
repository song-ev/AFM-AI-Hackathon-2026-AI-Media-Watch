from django.urls import path
from .views import ScreeningResultView

app_name = "screening"

urlpatterns = [
    path('<int:video_id>/result/', ScreeningResultView.as_view(), name='screening-result'),
]
