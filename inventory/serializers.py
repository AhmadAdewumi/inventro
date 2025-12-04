from rest_framework import serializers
from django.contrib.auth.models import User, Group
from .models import ProductVariant, Order, Supplier, PurchaseOrder, PurchaseOrderItem, OrderItem, InventoryLog

#-- just like dto + mappers in Java, Ahh, I miss Java
class ProductVariantSerializer(serializers.ModelSerializer):
    #--Instead of { "product": { "name": "Nike" } }, we want { "product_name": "Nike" }
    product_name = serializers.CharField(source = 'product.name')
    category = serializers.CharField(source = 'product.category')

    class Meta:
        model = ProductVariant

        #-- we list  the fields to be exposed to FE
        fields = [
            'id', 'sku', 'barcode', 'product_name', 'category', 
            'name_suffix', 'price', 'stock_quantity'
        ]

class PurchaseItemSerializer(serializers.Serializer):
    #--validates single item in cart
    barcode = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)
    discount_percent = serializers.IntegerField(required=False, default=0, min_value=0, max_value=100) #-- optional, default to 0, if not provided

class PurchaseSerializer(serializers.Serializer):
    #-- validates the whole request, tells DRF to expect  alist of item objects, each validated using PurchaseItemSerializer
    payment_method = serializers.ChoiceField(choices=Order.PAYMENT_METHODS)
    items = PurchaseItemSerializer(many=True)

class InventoryAdjustmentSerializer(serializers.Serializer):
    barcode = serializers.CharField()
    quantity_change = serializers.IntegerField() #-- if positive, stock added, else, stock reduced

    action = serializers.ChoiceField(choices=[
        ('sale', 'Sale'),           # POS transaction
        ('restock', 'Restock'),     # Supplier delivery
        ('audit', 'Audit/Manual Correction'), # Manager manuallly fixing count
        ('loss', 'Damage / Theft'),   # Broken item
    ])

    #-- optional note, say "Restocked 50 coke bottles" // "Fell On floor and broke...."
    note = serializers.CharField(required=False, allow_blank=True)

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source='variant.barcode', read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'variant', 'barcode', 'product_name', 'quantity', 'unit_cost']

class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = ['id', 'supplier', 'supplier_name', 'status', 'total_cost', 'created_at', 'items']

#-- Input Serializer for creating a Purchase Order
class CreatePurchaseOrderSerializer(serializers.Serializer):
    supplier_id = serializers.IntegerField()
    items = serializers.ListField(
        child=serializers.DictField() #--expects: {'variant_id': 1, 'quantity': 10, 'cost': 50.00}
    )

class RefundItemSerializer(serializers.Serializer):
    barcode = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)
    is_damaged = serializers.BooleanField(default=False)

class RefundSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    items = RefundItemSerializer(many=True)

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='variant.product.name')
    sku = serializers.CharField(source='variant.sku')
    barcode = serializers.CharField(source='variant.barcode')

    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'sku', 'barcode', 'quantity', 'refunded_quantity', 'unit_price']

class OrderSerializer(serializers.ModelSerializer):
    cashier_name = serializers.CharField(source='cashier.username')
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'created_at', 'total_amount', 'payment_method', 'status', 'cashier_name', 'items']

class InventoryLogSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    sku = serializers.CharField(source='variant.sku', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = InventoryLog
        fields = ['id', 'action', 'quantity_change', 'stock_after', 'note', 'created_at', 'product_name', 'sku', 'user_name']


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id', 'username', 'is_active', 'date_joined', 'role']

    def get_role(self, obj):
        if obj.is_superuser: return "Owner"
        return obj.groups.first().name if obj.groups.exists() else "Staff"
    
class CreateUserSerializer(serializers.ModelSerializer):
    #-- we are handling role manually because it is not a field on User model, it's a relationship
    role = serializers.ChoiceField(choices=['Cashier', 'Manager'], write_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password', 'role']

    def create(self, validated_data):
        role_name = validated_data.pop('role')
        password = validated_data.pop('password')
        
        #-- create_user handles password hashing automatically
        user = User.objects.create_user(password=password, **validated_data)
        
        group, _ = Group.objects.get_or_create(name=role_name)
        user.groups.add(group)
        
        return user