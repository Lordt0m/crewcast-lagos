from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    health_check_view,
    job_board_view,
    job_detail_view,
    job_create_view,
    job_edit_view,
    site_create_view,
    policy_edit_view,
    operations_view,
    demo_replay_view,
)

urlpatterns = [
    # Health checks
    path('health/', health_check_view, name='health_check'),
    path('healthz/', health_check_view, name='healthz'),

    # Board and details
    path('', job_board_view, name='job_board'),
    path('jobs/<int:pk>/', job_detail_view, name='job_detail'),
    path('jobs/new/', job_create_view, name='job_create'),
    path('jobs/<int:pk>/edit/', job_edit_view, name='job_edit'),
    path('sites/new/', site_create_view, name='site_create'),
    path('policy/', policy_edit_view, name='policy_edit'),

    # Operations & Demo Replay
    path('operations/', operations_view, name='operations'),
    path('demo/replay/', demo_replay_view, name='demo_replay'),

    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
