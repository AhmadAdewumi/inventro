from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Notification
from .models import (Order, OrderItem,
                     InventoryLog, PurchaseOrder, PurchaseOrderItem,
                     Supplier, Product, ProductVariant, Customer,
                     StocktakeSession, StocktakeItem
                     )
from .pricing import calculate_dynamic_price
from .utils import generate_barcode_pdf


#-- felt like home a litle bit, but this is actually a weird way of defining types (only for readbility, nah nah, it doesn't even use it)
def get_product_by_barcode(barcode: str) -> ProductVariant: #-- retunrs ProductVariant
    #-- check db for product with barcodee, raises error if not found
    try:
        #-- select_realted is like @EntityGraph in spring boot to eagerly fetch child entities without double db trip
        variant = ProductVariant.objects.select_related('product').get(barcode = barcode)
        return variant
    except ProductVariant.DoesNotExist:
        return None
    
def process_purchase(user, payment_method, items_data, customer_id=None, is_quote = False):
    """
    Handles Sales, including Debt and Wallet payments.
    """
    with transaction.atomic():
        customer = None
        if customer_id:
            try:
                customer = Customer.objects.get(id=customer_id)
            except Customer.DoesNotExist:
                raise ValidationError("Invalid Customer ID")

        status = 'quote' if is_quote else 'completed'
        final_payment_method = 'none' if is_quote else payment_method

        # Create Order
        order = Order.objects.create(
            cashier=user,
            status='completed',
            payment_method=payment_method,
            total_amount=Decimal('0.00'),
            customer=customer # Link customer
        )

        total_sum = Decimal('0.00')

        # ... (Loop through items, check stock, create OrderItems) ...
        for item in items_data:
            barcode = item['barcode']
            qty = item['quantity']
            manual_discount = item.get('discount_percent', 0)
            
            try:
                #-- we lock row if it is a real sale, and just read it if it is a quote
                if not is_quote:
                    variant = ProductVariant.objects.select_for_update().get(barcode=barcode)
                else:
                    variant = ProductVariant.objects.get(barcode=barcode)
            except ProductVariant.DoesNotExist:
                raise ValidationError(f"Product {barcode} not found.")
            
            if not is_quote and variant.stock_quantity < qty:
                raise ValidationError(f"Not enough stock for {variant.product.name}. Available: {variant.stock_quantity}")
            
            final_unit_price = calculate_dynamic_price(variant, qty, manual_discount)
            
            OrderItem.objects.create(order=order, variant=variant, quantity=qty, unit_price=final_unit_price)

            #-- we only update thw stock and logs for real sale
            if not is_quote:
                variant.stock_quantity -= qty
                variant.save()

                InventoryLog.objects.create(
                    variant=variant, user=user, action='sale', quantity_change=-qty,
                    stock_after=variant.stock_quantity, note=f"Order #{order.id}"
                )

                #-- LOW STOCK ALERT
                if variant.stock_quantity <= 5:
                    #-- we check if alert already exists to avoid spamming
                    recent_alert = Notification.objects.filter(
                        title = "Low Stock Alert",
                        message__contains=variant.sku,
                        is_read=False
                    ).exists()

                    if not recent_alert:
                        Notification.objects.create(
                            title="Low Stock Alert",
                            message=f"{variant.product.name} ({variant.name_suffix}) is low. {variant.stock_quantity} left.",
                            link="inventory"
                        )
            total_sum += (final_unit_price * qty)

        order.total_amount = total_sum
        order.save()

        #-- we handle Debt/Pay from wallet only for Real Sales
        if not is_quote:
            if payment_method == 'debt':
                if not customer: raise ValidationError("Customer required for Debt")
                customer.wallet_balance -= total_sum
                customer.save()
            elif payment_method=='wallet':
                if not customer: raise ValidationError("Customer required")
                if customer.wallet_balance < total_sum: raise ValidationError("Insufficient wallet funds")
                customer.wallet_balance -= total_sum
                customer.save()
        return order

        # # -- HANDLE DEBT/WALLET LOGIC
        # if payment_method == 'debt':
        #     if not customer:
        #         raise ValidationError("Customer required for Debt payments.")
        #     #-- debt decreases balance (becomes negative)
        #     customer.wallet_balance -= total_sum
        #     customer.save()
        #
        # elif payment_method == 'wallet':
        #     if not customer:
        #         raise ValidationError("Customer required for Wallet payments.")
        #     if customer.wallet_balance < total_sum:
        #         raise ValidationError(f"Insufficient funds. Balance: {customer.wallet_balance}")
        #     #-- deduct from pre-paid balance
        #     customer.wallet_balance -= total_sum
        #     customer.save()
        #
        # return order
    
#-- for manual inventory adjustment
def adjust_inventory(user, data):
    """
    This handles restocking, damages and manual corrections
    """
    with transaction.atomic():
        barcode = data['barcode']
        qty_change = data['quantity_change']
        action = data['action']
        note = data.get('note', '')

        #-- lock the product/item in case of concurrent update, pessimistic locking by the way
        try:
            variant = ProductVariant.objects.get(barcode=barcode)
        except ProductVariant.DoesNotExist:
            raise ValidationError(f"Product Variant with barcode: {barcode} not found")
        
        new_stock_quantity = variant.stock_quantity + qty_change

        if new_stock_quantity < 0:
            raise ValidationError(f"Cannot reduce stock below zero. Current: {variant.stock_quantity}")
        
        #-- persist
        variant.stock_quantity = new_stock_quantity
        variant.save()

        #--we write to inventory log also
        InventoryLog.objects.create(
            variant = variant,
            user = user,
            action = action,
            quantity_change = qty_change,
            stock_after = new_stock_quantity,
            note = note
        )

        return variant
    
def get_dashboard_stats():
    """
    High level view for admin dashboard
    """
    today = timezone.now().date()

    #-- 1. Total sales for today (total revenue)
    #-- filter out orders from today that are completed
    #-- the total sales for today
    todays_orders = Order.objects.filter(
        created_at__date = today,
        status = 'completed'
    )

    #-- aggregate() returms a single dictionary for the whole table, e.g {'total_revenue:5000'}, justy like SQL SUM
    #-- we sum the total amount column
    revenue_data = todays_orders.aggregate(total_revenue=Sum('total_amount'))
    total_revenue = revenue_data['total_revenue'] or 0

    #--2.  now to calculate the total profit made today
    #-- profit = CP -SP
    profit_data = OrderItem.objects.filter(
        order__created_at__date = today,
        order__status = 'completed'
    ).aggregate(
        total_profit = Sum(
            (F('unit_price') - F('variant__cost_price')) * F('quantity')
        )
    )
    total_profit = profit_data['total_profit'] or 0

    #-- 3. low stock count
    low_stock_count = ProductVariant.objects.filter(stock_quantity__lt=10).count()

    return {
        "date" : today,
        "revenue" : total_revenue,
        "profit" : total_profit,
        "low_stock_items" : low_stock_count
    }

def get_top_selling_items():
    """
    This gets the top 5 sold items by quantity sold, this is where annotate() i.e GROUP_BY in SQL comes in
    """
    """
    -- we start with the order items,
    -- group them by the variant name,
    -- sum the quantity
    -- and then order by the biggest sum(desc)
    """
    return OrderItem.objects.values(
        'variant__product__name',
        'variant__name_suffix'
    ).annotate(
        total_sold = Sum('quantity'),
        total_revenue=Sum(F('unit_price') - F('quantity'))
    ).order_by('-total_sold')[:5] #-- limit 5

def receive_purchase_order(user, purchase_order_id):
    """
    -- this finalizes a purchase order
    1.locks the db, in case of concurrent update, pessimistic locking
    2. updates stocks for all  items
    3. updates the product cost prices as it may have changed
    4. we log the changes
    """

    with transaction.atomic():
        #-- we fetch the purchase order
        try:
            purchase_order = PurchaseOrder.objects.select_for_update().get(id = purchase_order_id)
        except PurchaseOrder.DoesNotExist:
            raise ValidationError("Purchase Order Not Found")
        
        if purchase_order.status == 'received':
            raise ValidationError("This purchase order has beeen reieved already")
        
        all_items = purchase_order.items.all()
        
        for item in all_items:
            variant = item.variant

            #-- locking the row for update
            variant = ProductVariant.objects.select_for_update().get(id=variant.id)

            # old_stock = variant.stock_quantity
            # new_stock = old_stock + item.quantity

            current_stock = Decimal(variant.stock_quantity)
            current_cost = variant.cost_price
            incoming_qty = Decimal(item.quantity)
            incoming_cost = item.unit_cost

            if current_stock <= 0:
                new_cost = incoming_cost
            else:
                # 2. Calculate AVCO(Average Cost)
                # Formula: ((OldQty * OldCost) + (NewQty * NewCost)) / (OldQty + NewQty)
                total_value = (current_stock * current_cost) + (incoming_qty * incoming_cost)
                total_qty = current_stock + incoming_qty
                new_cost = total_value / total_qty

            #-- stock update
            variant.stock_quantity = int(current_stock + incoming_qty)

            #-- update the CP
            variant.cost_price = item.unit_cost

            variant.save()

            #-- inventory log (audit)
            InventoryLog.objects.create(
                variant=variant,
                user=user,
                action='restock',
                quantity_change=item.quantity,
                stock_after=variant.stock_quantity,
                note=f"PO #{purchase_order.id} (Average Cost: {variant.cost_price})"
            )
        
        #-- we mark the purchase order as received
        purchase_order.status = 'received'
        purchase_order.received_date = timezone.now()
        purchase_order.save()

        Notification.objects.create(
            title="Stock Received",
            message=f"Purchase Order #{purchase_order.id} from {purchase_order.supplier.name} has been added to inventory.",
            link="procurement"
        )

        return purchase_order
    

def process_refund(user, order_id, refund_items):
    with transaction.atomic():
        try:
            order = Order.objects.get(id=order_id) #-- we get the order
        except:
            raise ValidationError("Order Not Found")

        total_refund = 0

        for item in refund_items:
            barcode=item['barcode'] #-- must be provided, that is hwy we access the element like that, KeyError is thrown if not provided
            qty= item['quantity'] #-- same , 'this is the qty the user is trying to return right now'
            is_damaged= item.get('is_damaged', False) #-- optional, that is why we use get(), if key exists, return the value, if not, return False

            try:
                #-- We filter by order=order AND barcode to find the specific item in this order
                order_item = OrderItem.objects.get(order=order, variant__barcode=barcode)
            except OrderItem.DoesNotExist:
                raise ValidationError(f"Item {barcode} not in this order.")
            except OrderItem.MultipleObjectsReturned:
                #--If duplicate items exist in one order, assume the first one
                order_item = OrderItem.objects.filter(order=order, variant__barcode=barcode).first()
            
            returnable = order_item.quantity - order_item.refunded_quantity #-- we calculate the qty the user can still return to mitigate fraud
            if qty > returnable:#-- if what the user wants to return is more than the qty he can return
                raise ValidationError(f"Cannot return {qty}. Only {returnable} eligible.")
            
            order_item.refunded_quantity += qty #--- if they are allowed to refund the quantity, we add it to the already refunded total
            order_item.save()

            variant = order_item.variant
            if is_damaged: #-- we do not touch the existing stock, just create a loss log
                InventoryLog.objects.create(
                    variant=variant, user=user, action='loss', quantity_change=0,
                    stock_after=variant.stock_quantity, note=f"Damaged Return: Order #{order.id}"
                )
            else:
                variant = ProductVariant.objects.select_for_update().get(id=variant.id)
                new_stock = variant.stock_quantity + qty
                variant.stock_quantity = new_stock
                variant.save()
                InventoryLog.objects.create(
                    variant=variant, user=user, action='restock', quantity_change=qty,
                    stock_after=new_stock, note=f"Return: Order #{order.id}"
                )

            total_refund += (order_item.unit_price * qty)

            if order.status == 'completed':
                order.status = 'refunded' 
                order.save()

        return {"order_id": order.id, "refunded_total": total_refund}
    
def create_product_and_variant(data):
    with transaction.atomic():
        #-- we create or get parent product
        product, _ = Product.objects.get_or_create(
            name=data['name'],
            defaults={
                'category' : data.get('category', 'General')
            }
        )

        #-- variant creation
        variant = ProductVariant.objects.create(
            product=product,
            sku=data['sku'],
            barcode=data['barcode'],
            price=data['price'],
            cost_price=data.get('cost', 0),
            stock_quantity=data.get('stock', 0),
            name_suffix=data.get('variant_name', 'Standard')
        )

        return variant

def get_barcode_pdf_buffer(category_query = None, variant_ids=None):
    """
    Service to fetch variants based on filters and return a PDF buffer.
    """
    variants = ProductVariant.objects.select_related('product').all().order_by('product__category', 'product__name')
    
    if variant_ids:
        #-- if specific IDs are requested, filter only those ids and generarte barcodes for them
        variants = variants.filter(id__in=variant_ids)
    elif category_query:
        variants = variants.filter(product__category__icontains=category_query) #-- fall back to category filter

    return generate_barcode_pdf(variants)
    
def create_purchase_order(user, data):
    """
    Creates a Draft Purchase Order and its items transactionally.
    """
    with transaction.atomic():
        try:
            supplier = Supplier.objects.get(id=data['supplier_id'])
        except Supplier.DoesNotExist:
            raise ValidationError("Supplier not found.")

        # 1. Create Header
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            created_by=user,
            status='draft'
        )

        total_cost = 0
        
        # 2. Create Items
        for item in data['items']:
            try:
                variant = ProductVariant.objects.get(id=item['variant_id'])
            except ProductVariant.DoesNotExist:
                raise ValidationError(f"Variant ID {item['variant_id']} not found.")
                
            qty = item['quantity']
            cost = item['cost']
            
            PurchaseOrderItem.objects.create(
                purchase_order=purchase_order, 
                variant=variant, 
                quantity=qty, 
                unit_cost=cost
            )
            total_cost += (cost * qty)

        # 3. Update Total
        purchase_order.total_cost = total_cost
        purchase_order.save()
        
        return purchase_order
    
    #-- STOCK TAKING
    
def start_stocktake(user, note=""):
    """
    Snapshots the entire inventory state into a new session.
    """
    with transaction.atomic():
        # 1. Create Session
        session = StocktakeSession.objects.create(created_by=user, note=note)
        
        # 2. Snapshot every product
        all_variants = ProductVariant.objects.filter(is_active=True) # Assuming you added is_active to Variant or Product

        # For now, let's grab all:
        # all_variants = ProductVariant.objects.all()
        
        items = []
        for v in all_variants:
            items.append(StocktakeItem(
                session=session,
                variant=v,
                expected_quantity=v.stock_quantity,
                counted_quantity=0 # Default start at 0 (Blind Count) or v.stock_quantity (Guided)
                # Let's default to 0 to force them to scan/count.
            ))
        
        StocktakeItem.objects.bulk_create(items)
        return session

def update_stocktake_item(session_id, barcode, qty):
    """
    Updates the count for a specific item in the session.
    """
    try:
        item = StocktakeItem.objects.get(session_id=session_id, variant__barcode=barcode)
        item.counted_quantity = qty
        item.save()
        return item
    except StocktakeItem.DoesNotExist:
        raise ValidationError("Item not found in this stocktake session")

def approve_stocktake(user, session_id):
    """
    Finalizes the count.
    Updates actual inventory to match the counted values.
    Logs discrepancies.
    """
    with transaction.atomic():
        session = StocktakeSession.objects.select_for_update().get(id=session_id)
        if session.status != 'in_progress':
            raise ValidationError("Session already closed")
            
        for item in session.items.all():
            variance = item.counted_quantity - item.expected_quantity
            
            if variance != 0:
                # We need to adjust the real stock
                variant = ProductVariant.objects.select_for_update().get(id=item.variant.id)
                
                # Logic: We overwrite stock to match the count
                # But we log the *difference*
                variant.stock_quantity = item.counted_quantity
                variant.save()
                
                action = 'restock' if variance > 0 else 'loss'
                note = f"Stocktake #{session.id} (Variance: {variance})"
                
                InventoryLog.objects.create(
                    variant=variant,
                    user=user,
                    action=action,
                    quantity_change=variance,
                    stock_after=item.counted_quantity,
                    note=note
                )

        has_variance = False
        for item in session.items.all():
            variance = item.counted_quantity - item.expected_quantity
            if variance != 0:
                has_variance = True

        session.status = 'completed'
        session.completed_at = timezone.now()
        session.save()

        msg = "Stocktake completed with discrepancies." if has_variance else "Stocktake completed perfectly."
        Notification.objects.create(title="Stocktake Finished", message=msg, link="audit")

        return session