from django.contrib import admin
from django.http import FileResponse
from .models import (
    Product, ProductVariant, Order, OrderItem, InventoryLog,
    Promotion, Supplier, PurchaseOrder, PurchaseOrderItem
)
from .services import receive_purchase_order
from .utils import generate_barcode_pdf

#-- Product & Variants
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

#-- Orders
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['unit_price']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = ['id', 'cashier', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']

#-- Logs & Promos
@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'variant', 'action', 'quantity_change', 'user']
    list_filter = ['action']

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_quantity', 'discount_percent', 'is_active']

#-- Procurement
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email']

class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    inlines = [PurchaseOrderItemInline]
    list_display = ['id', 'supplier', 'status', 'total_cost', 'created_at']
    list_filter = ['status']
    actions = ['mark_as_received']

    @admin.action(description='Receive Stock (Finalize PO)')
    def mark_as_received(self, request, queryset):
        for purchase_order in queryset:
            if purchase_order.status == 'received':
                continue
            try:
                receive_purchase_order(request.user, purchase_order.id)
                self.message_user(request, f"Received PO #{purchase_order.id}")
            except Exception as e:
                self.message_user(request, f"Error: {str(e)}", level='error')