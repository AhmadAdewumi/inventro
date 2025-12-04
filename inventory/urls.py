from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (ScanItemView, PurchaseView, InventoryAdjustmentView, 
                    DashboardStatsView, TopSellingProductView,
                      store_os_view, logout_view, SupplierListView, ProductListView,
                      PurchaseOrderView,ReceivePurchaseOrderView, RefundView, OrderListView,
                      PurchaseOrderListView, AuditLogView, BarcodeGeneratorView,
                      UserMetaView, StaffActionView, StaffView
)

urlpatterns = [
    #-- UI
    path('', store_os_view, name='store_os'),
    path('login/', auth_views.LoginView.as_view(template_name='inventory/login.html'), name='login'),
    path('logout/', logout_view, name='logout'),

    #-- User & Staff
    path('api/me/', UserMetaView.as_view(), name='user-meta'),
    path('api/staff/', StaffView.as_view(), name='staff-list'),
    path('api/staff/<int:user_id>/toggle/', StaffActionView.as_view(), name='staff-toggle'),

    #-- POS & Sales
    path('api/scan/<str:barcode>/', ScanItemView.as_view(), name='scan-item'),
    path('api/purchase/', PurchaseView.as_view(), name='purchase'),
    path('api/orders/', OrderListView.as_view(), name='order-list'),
    path('api/refund/', RefundView.as_view(), name='refund'),

    #-- Inventory
    path('api/products/', ProductListView.as_view(), name='product-list'),
    path('api/adjust/', InventoryAdjustmentView.as_view(), name='inventory_adjust'),
    path('api/print-labels/', BarcodeGeneratorView.as_view(), name='print-labels'),
    
    #-- Procurement
    path('api/suppliers/', SupplierListView.as_view(), name='suppliers'),
    path('api/po/create/', PurchaseOrderView.as_view(), name='create-po'),
    path('api/po/list/', PurchaseOrderListView.as_view(), name='po-list'),
    path('api/po/<int:po_id>/receive/', ReceivePurchaseOrderView.as_view(), name='receive-po'),
    
    #-- Reports & Audit
    path('api/reports/dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('api/reports/top-selling/', TopSellingProductView.as_view(), name='top-selling'),
    path('api/logs/', AuditLogView.as_view(), name='audit-logs'),
]