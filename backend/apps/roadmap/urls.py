from django.urls import path

from apps.roadmap.views import PublicRoadmapListView


urlpatterns = [
    path("public/roadmap", PublicRoadmapListView.as_view(), name="public-roadmap"),
]
