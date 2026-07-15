from django.urls import path

from apps.machines.views_public import PublicMachineListView


urlpatterns = [
    path(
        'public/<slug:makerspace_slug>/machines',
        PublicMachineListView.as_view(),
        name='public-machines',
    ),
]
