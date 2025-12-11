from decimal import Decimal

from django.db.models import Q

from .models import Promotion


def calculate_dynamic_price(variant, quantity, manual_discount_percent = 0):
    """
    Calculates the final unit price by looking up Rules in the DB.
    
    Arguments:
    - variant: The item being sold.
    - quantity: How many are being bought (for volume discounts).
    - manual_discount_percent: The 'Preference' discount given by the cashier (0-100).
    """
    unit_price = variant.price

    applicable_promos = Promotion.objects.filter(
        is_active = True, #-- we only use promos that are active
        min_quantity__lte=quantity #-- only promos whose minimum required quantity is less than or equal to what the customer is buying
    ).filter(
        Q(variant=variant) | Q(variant__isnull=True) #-- promotions that are specifically for this product variant or that are general
    ).order_by('-discount_percent') #-- highest discount comes first

    if applicable_promos.exists():
        best_rule = applicable_promos.first()
        db_multiplier = (Decimal(100) - Decimal(best_rule.discount_percent)) / Decimal(100)
        unit_price = unit_price * db_multiplier

    if manual_discount_percent > 0:
        manual_multiplier = (Decimal(100) - Decimal(manual_discount_percent)) / Decimal(100)
        unit_price = unit_price * manual_multiplier
        
    return round(unit_price, 2)

