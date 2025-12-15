from django.contrib.auth import views as auth_views
from django.urls import path

from .views import (ScanItemView, PurchaseView, InventoryAdjustmentView,
                    DashboardStatsView, TopSellingProductView,
                    store_os_view, logout_view, SupplierListView, ProductListView,
                    PurchaseOrderView, ReceivePurchaseOrderView, RefundView, OrderListView,
                    PurchaseOrderListView, AuditLogView, BarcodeGeneratorView,
                    UserMetaView, StaffActionView, StaffView,
                    ExportSalesView, ExportInventoryView, DatabaseBackupView, CustomerView,
                    receipt_view, StocktakeListView, StocktakeDetailView, StoreSettingsView, NotificationView,
                    OrderDetailView, CustomerDetailView, SupplierDetailView, ProductDetailView, StaffDetailView
                    )

urlpatterns = [
    # -- UI
    path('', store_os_view, name='store_os'),
    path('login/', auth_views.LoginView.as_view(template_name='inventory/login.html'), name='login'),
    path('logout/', logout_view, name='logout'),

    # -- User & Staff
    path('api/me/', UserMetaView.as_view(), name='user-meta'),
    path('api/staff/', StaffView.as_view(), name='staff-list'),
    path('api/staff/<int:user_id>/toggle/', StaffActionView.as_view(), name='staff-toggle'),

    # -- POS & Sales
    path('api/scan/<str:barcode>/', ScanItemView.as_view(), name='scan-item'),
    path('api/purchase/', PurchaseView.as_view(), name='purchase'),
    path('api/orders/', OrderListView.as_view(), name='order-list'),
    path('api/refund/', RefundView.as_view(), name='refund'),

    # -- Inventory
    path('api/products/', ProductListView.as_view(), name='product-list'),
    path('api/adjust/', InventoryAdjustmentView.as_view(), name='inventory_adjust'),
    path('api/print-labels/', BarcodeGeneratorView.as_view(), name='print-labels'),

    # -- Procurement
    path('api/suppliers/', SupplierListView.as_view(), name='suppliers'),
    path('api/po/create/', PurchaseOrderView.as_view(), name='create-po'),
    path('api/po/list/', PurchaseOrderListView.as_view(), name='po-list'),
    path('api/po/<int:po_id>/receive/', ReceivePurchaseOrderView.as_view(), name='receive-po'),

    # -- Reports & Audit
    path('api/reports/dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('api/reports/top-selling/', TopSellingProductView.as_view(), name='top-selling'),
    path('api/logs/', AuditLogView.as_view(), name='audit-logs'),

    # EXPORTS & BACKUPS
    path('api/export/sales/', ExportSalesView.as_view(), name='export-sales'),
    path('api/export/inventory/', ExportInventoryView.as_view(), name='export-inventory'),
    path('api/backup/', DatabaseBackupView.as_view(), name='backup-db'),

    # Customers
    path('api/customers/', CustomerView.as_view(), name='customers'),

    # __ receipt
    path('print/receipt/<int:order_id>/', receipt_view, name='print-receipt'),

    # --Stock Taking
    path('api/stocktake/', StocktakeListView.as_view(), name='stocktake-list'),
    path('api/stocktake/<int:pk>/', StocktakeDetailView.as_view(), name='stocktake-detail'),

    path('api/settings/', StoreSettingsView.as_view(), name='settings'),
    path('api/notifications/', NotificationView.as_view(), name='notifications'),
    path('api/notifications/<int:pk>/read/', NotificationView.as_view(), name='read-notification'),

    # -- deletions
    path('api/orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('api/customers/<int:pk>/', CustomerDetailView.as_view(), name='customer-detail'),
    path('api/suppliers/<int:pk>/', SupplierDetailView.as_view(), name='supplier-detail'),
    path('api/products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('api/staff/<int:pk>/', StaffDetailView.as_view(), name='staff-detail'),
]
