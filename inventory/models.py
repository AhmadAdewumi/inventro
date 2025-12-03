from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True) #-- soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)

    #-- identification
    sku = models.CharField(max_length=50, unique=True) #-- Stock Keepng Unit
    barcode = models.CharField(max_length=50, unique=True)

    name_suffix = models.CharField(max_length=100) #-- e.g. "Size L - Red"

    #-- core business data
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=20,decimal_places=2, help_text="Cost Price of the product from the supplier" )

    stock_quantity = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} - {self.name_suffix}"
    
#_------------- Transactions 

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'), #-- in cart
        ('completed', 'Completed'), #-- paid
        ('refunded', 'Refunded') #-- returned
    ]

    PAYMENT_METHODS =[
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('transfer', 'Transfer'),
    ]

    cashier =  models.ForeignKey(
        User,
        related_name='orders',
        on_delete=models.PROTECT
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status =  models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.status}"
    
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, related_name='order_items', on_delete=models.PROTECT)

    quantity = models.IntegerField(default=1)
    #-- We freeze the price at the moment of sale.
    # Even if ProductVariant.price changes later, this record remains historically accurate.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    refunded_quantity = models.IntegerField(default=0)

    def get_total_price(self):
        return self.quantity * self.unit_price
    
    def __str__(self):
        return f"{self.quantity} - {self.variant.sku}"
    

class InventoryLog(models.Model):
    """
    -- Every time stock changes, we write a row here.
    """
    ACTION_CHOICES = [
        ('sale', 'Sale'),           # POS transaction
        ('restock', 'Restock'),     # Supplier delivery
        ('audit', 'Audit/Correction'), # Manager manuallly fixing count
        ('loss', 'Damage/Theft'),   # Broken item
    ]

    variant = models.ForeignKey(ProductVariant, related_name='logs', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity_change = models.IntegerField() # e.g -1 for sale, +10 for restock
    
    #--Snapshot of stock after the change
    stock_after = models.IntegerField() 
    
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)



class Promotion(models.Model):
    #--- allows the owner to define dynamic rules, e.g discount for bulk purchase
    name = models.CharField(max_length=100) #-- e.g wholesale discount
    is_active = models.BooleanField(default=True)
    #--condition, like if they buy X quantity, apply this discount
    min_quantity = models.IntegerField(default=1)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, help_text="0 to 100")

    # Target: Specific Product? Or Global?
    # If null, it applies to EVERYTHING in the store (e.g. "Black Friday 10% off everything")
    variant = models.ForeignKey(ProductVariant, null =True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        target = self.variant.name_suffix if self.variant else "Global"
        return f"{self.name}: Buy {self.min_quantity}+ get {self.discount_percent}% off ({target})"
    


class Supplier(models.Model):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name
    

    
class PurchaseOrder(models.Model):
    STATUS_CHOICES =[
        ('draft', 'Draft'), #--planning to order
        ('ordered', 'Ordered'), #-- order sent to supplier
        ('received', 'Received'), #--order arrived
        ('canceled', 'Canceled')
    ]

    supplier = models.ForeignKey(Supplier, related_name='orders', on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateTimeField(null=True, blank=True)

    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Purchase Order #{self.id} - {self.supplier.name}"
    

    
class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, related_name='items', on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, related_name='purchase_order_items', on_delete=models.PROTECT)
    quantity = models.IntegerField()
    #--cost price per item for this specific shipment
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    def get_total(self):
        return self.quantity * self.unit_cost
    