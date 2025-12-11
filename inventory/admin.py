from django.contrib import admin
from django.http import FileResponse

from .models import (
    Product, ProductVariant, Order, OrderItem, InventoryLog,
    Promotion, Supplier, PurchaseOrder, PurchaseOrderItem, Notification, StoreSettings, StocktakeSession, StocktakeItem,
    Customer
)
from .services import receive_purchase_order
from .utils import generate_barcode_pdf


# -- Product & Variants
class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductVariantInline]
    list_display = ['name', 'category', 'created_at']


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['sku', 'product', 'barcode', 'price', 'stock_quantity']
    search_fields = ['barcode', 'sku', 'product__name']
    actions = ['print_labels']

    @admin.action(description='Print Barcode Labels')
    def print_labels(self, request, queryset):
        pdf_buffer = generate_barcode_pdf(queryset)
        return FileResponse(pdf_buffer, as_attachment=True, filename='barcodes.pdf')


# -- Orders
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    readonly_fields = ['unit_price']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = ['id', 'cashier', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']


# -- Logs & Promos
@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'variant', 'action', 'quantity_change', 'user']
    list_filter = ['action']


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_quantity', 'discount_percent', 'is_active']


# -- Procurement
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email']


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'wallet_balance', 'created_at']
    search_fields = ['name', 'phone']


class StocktakeItemInline(admin.TabularInline):
    model = StocktakeItem
    extra = 0
    readonly_fields = ['variant', 'expected_quantity', 'counted_quantity']


@admin.register(StocktakeSession)
class StocktakeSessionAdmin(admin.ModelAdmin):
    inlines = [StocktakeItemInline]
    list_display = ['id', 'created_by', 'status', 'created_at']
    list_filter = ['status']


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ['store_name', 'phone', 'email']

    # Prevent creating multiple settings in admin
    def has_add_permission(self, request):
        return not StoreSettings.objects.exists()


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_read', 'created_at']
    list_filter = ['is_read']


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    inlines = [PurchaseOrderItemInline]
    list_display = ['id', 'supplier', 'status', 'total_cost', 'created_at']
    list_filter = ['status']
    actions = ['mark_as_received']

    @admin.action(description='Receive Stock (Finalize Purchase Order)')
    def mark_as_received(self, request, queryset):
        # -- A QuerySet represents a collection of objects from the database.  (Django docs)
        # It can have zero, one or many filters. Filters narrow down the query results based on the given parameters.
        #  In SQL terms, a QuerySet equates to a SELECT statement, and a filter is a limiting clause such as WHERE or LIMIT.
        for purchase_order in queryset:  # -- grabs each selected purchase order
            if purchase_order.status == 'received':
                continue
            try:
                receive_purchase_order(request.user, purchase_order.id)
                self.message_user(request, f"Received Purchase Order #{purchase_order.id}")
            except Exception as e:
                self.message_user(request, f"Error: {str(e)}",
                                  level='error')  # -- message user is used to show feedback messages at the top of the admin page
