from django.urls import path

from apps.machines.views_public import PublicMachineListView
from apps.machines.views_public_service import PublicMachineServiceSubmitView


urlpatterns = [
    path(
        'public/<slug:makerspace_slug>/machines',
        PublicMachineListView.as_view(),
        name='public-machines',
    ),
    path(
        'public/<slug:makerspace_slug>/machine-service-requests',
        PublicMachineServiceSubmitView.as_view(),
        name='public-machine-service-request-submit',
    ),
]
