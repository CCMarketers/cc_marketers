# subscriptions/urls.py
from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('', views.subscription_plans, name='plans'),
    path('subscribe/<int:plan_id>/', views.subscribe, name='subscribe'),
    path('my-subscription/', views.my_subscription, name='my_subscription'),
    path('toggle-auto-renewal/', views.toggle_auto_renewal, name='toggle_auto_renewal'),
    path('cancel/', views.cancel_subscription, name='cancel_subscription'),
]

