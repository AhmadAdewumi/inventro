from django.contrib import admin
from .models import (Product, ProductVariant, Order, OrderItem, InventoryLog, Promotion,
                     Supplier, PurchaseOrder, PurchaseOrderItem                     
                     )
from django.utils.html import format_html
from .services import receive_purchase_order
from django.http import FileResponse
from .utils import generate_barcode_pdf

# Register your models here.

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductVariantInline]
    list_display = ['name', 'category', 'created_at']

#-- order history
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['unit_price']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = ['id', 'cashier', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']

@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'variant', 'action', 'quantity_change', 'user', 'stock_after']
    list_filter = ['action', 'created_at']
    search_fields = ['variant__sku', 'user__username']

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_quantity', 'discount_percent', 'is_active', 'variant']
    list_editable = ['is_active']
    list_filter = ['is_active']
    help_text = "Manage automatic pricing rules here."

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email']
    search_fields = ['name']

# 2. Purchase Order Items (Inline)
class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1

# 3. Purchase Orders
@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    inlines = [PurchaseOrderItemInline]
    list_display = ['id', 'supplier', 'status_badge', 'total_cost', 'created_at']
    list_filter = ['status', 'created_at']
    actions = ['mark_as_received'] # Register the custom button

    def status_badge(self, obj):
        # Color-coded status badges
        colors = {
            'draft': 'gray',
            'ordered': 'blue',
            'received': 'green',
            'canceled': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 5px;">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'

    @admin.action(description='Receive Stock (Finalize Purchase Order)')
    def mark_as_received(self, request, queryset):
        """
        Calls the service layer for selected POs.
        """
        for purchase_order in queryset:
            if purchase_order.status == 'received':
                self.message_user(request, f"PO #{purchase_order.id} is already received.", level='warning')
                continue
                
            try:
                # Call the Service Logic we wrote!
                receive_purchase_order(request.user, purchase_order.id)
                self.message_user(request, f"Successfully received stock for PO #{purchase_order.id}.")
            except Exception as e:
                self.message_user(request, f"Error on PO #{purchase_order.id}: {str(e)}", level='error')


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['sku', 'product', 'barcode', 'price', 'stock_quantity']
    search_fields = ['barcode', 'sku', 'product__name']
    actions = ['print_labels']

    @admin.action(description='Print Barcode Labels')
    def print_labels(self, request, queryset):
        """
        Generates a PDF for selected items.
        """
        pdf_buffer = generate_barcode_pdf(queryset)
        
        # Return as a downloadable file
        return FileResponse(
            pdf_buffer, 
            as_attachment=True, 
            filename='barcodes.pdf'
        )