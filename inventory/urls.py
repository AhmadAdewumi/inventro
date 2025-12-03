from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (ScanItemView, PurchaseView, InventoryAdjustmentView, 
                    DashboardStatView, TopSellingProductView,
                      store_os_view, logout_view, SupplierListView, ProductListView,
                      PurchaseOrderView,ReceivePurchaseOrderView, RefundView, OrderListView,
                      PurchaseOrderListView, AuditLogView, BarcodeGeneratorView
)

urlpatterns = [
    # 1. UI PAGES
    path('', store_os_view, name='store_os'),
    path('login/', auth_views.LoginView.as_view(template_name='inventory/login.html'), name='login'),
    path('logout/', logout_view, name='logout'),

    # 2. API ENDPOINTS (Must have 'api/' prefix to match React)
    path('api/scan/<str:barcode>/', ScanItemView.as_view(), name='scan-item'),
    path('api/purchase/', PurchaseView.as_view(), name='purchase'),
    path('api/adjust/', InventoryAdjustmentView.as_view(), name='inventory_adjust'),
    path('api/reports/dashboard/', DashboardStatView.as_view(), name='dashboard-stats'),
    path('api/reports/top-selling/', TopSellingProductView.as_view(), name='top-selling'),
    path('api/suppliers/', SupplierListView.as_view(), name='suppliers'),
    path('api/po/create/', PurchaseOrderView.as_view(), name='create-po'),
    path('api/po/<int:po_id>/receive/', ReceivePurchaseOrderView.as_view(), name='receive-po'),
    path('api/refund/', RefundView.as_view(), name='refund'),
    path('api/orders/', OrderListView.as_view(), name='order-list'),
    path('api/products/', ProductListView.as_view(), name = 'product-list'),
    path('api/po/list/', PurchaseOrderListView.as_view(), name='po-list'),
    path('api/logs/', AuditLogView.as_view(), name='audit-logs'),
    path('api/print-labels/', BarcodeGeneratorView.as_view(), name='print-labels'),
]