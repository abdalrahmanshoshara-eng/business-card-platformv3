from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BusinessCardViewSet, health

router = DefaultRouter()
router.register(r'cards', BusinessCardViewSet, basename='cards')

# Explicit no-slash aliases prevent Django from redirecting POST requests and losing form data.
cards_list = BusinessCardViewSet.as_view({'get': 'list', 'post': 'create'})
cards_detail = BusinessCardViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'put': 'update', 'delete': 'destroy'})
cards_extract = BusinessCardViewSet.as_view({'post': 'extract'})
cards_stats = BusinessCardViewSet.as_view({'get': 'stats'})
cards_stats_by_category = BusinessCardViewSet.as_view({'get': 'stats_by_category'})
cards_export = BusinessCardViewSet.as_view({'get': 'export_xlsx'})

urlpatterns = [
    path('health/', health),
    path('health', health),
    path('cards', cards_list),
    path('cards/<int:pk>', cards_detail),
    path('cards/<int:pk>/', cards_detail),
    path('cards/extract', cards_extract),
    path('cards/stats', cards_stats),
    path('cards/stats-by-category', cards_stats_by_category),
    path('cards/export-xlsx', cards_export),
    path('', include(router.urls)),
]
