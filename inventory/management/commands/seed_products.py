import random
from django.core.management.base import BaseCommand
from inventory.models import Product, ProductVariant

class Command(BaseCommand): #-- django manages this class and helps loading it using manage.py because  we inherited from BaseCommand
    help = 'Populates the DB with dummy products' #--help text shown when someone runs `python manage.py help seed_products`

    def handle(self, *args, **kwargs): #-- just like the main() method in java that serves as entry point, django calls this handle() method when the application runs
        categories = ['Drinks', 'Snacks', 'Electronics', 'Bakery', 'Produce']
        
        #-- Sample Data
        items = [ #-- a list of teuples, tuples used for internal data because the values are fixed  and won't change
            ("Pepsi", "Drinks", 50.00), #-- so, this is tuple and immutable, and tuple is faster and safe
            ("Mountain Dew", "Drinks", 55.00),
            ("Potato Chips", "Snacks", 25.00),
            ("Doritos", "Snacks", 30.00),
            ("Plantain", "Snacks", 15.00),
            ("USB Cable", "Electronics", 150.00),
            ("Charger Head", "Electronics", 300.00),
            ("Headphones", "Electronics", 500.00),
            ("Bread", "Bakery", 40.00),
            ("Cookies", "Bakery", 35.00),
            ("Apple", "Fruit", 5.00),
            ("Banana", "Fruit", 3.00),
        ]

        created_count = 0

        for name, cat, base_price in items:
            #-- Create Parent Product
            product, _ = Product.objects.get_or_create(
                name=name,
                defaults={'category': cat, 'description': f"Delicious {name}"}
            )

            #-- create  the product variants, each product get 2 variants, Pepsi large $ pepsi standard ....
            for suffix in ['Standard', 'Large']:
                #-- this generates a random 5-digit barcode
                #-- getting back to thios, TODO-- we  use a library or real scanner input, this is just to inject data to see if it works
                rand_barcode = str(random.randint(10000, 99999))
                
                #-- this checks if barcode exists to prevent crash, check for suplicate sha
                if ProductVariant.objects.filter(barcode=rand_barcode).exists():
                    continue

                sku = f"{name[:3].upper()}-{suffix[:1]}-{rand_barcode[:3]}" #-- string slicing, CSC201, memories
                price = base_price if suffix == 'Standard' else base_price * 1.5 #-- large is 50% more


                #-- if a product with the name exists, return it , if not, create wth default fields
                ProductVariant.objects.get_or_create(
                    sku=sku,
                    defaults={
                        'product': product,
                        'name_suffix': suffix,
                        'barcode': rand_barcode,
                        'price': price,
                        'cost_price': price * 0.7, #-- 30% margin from the S.P
                        'stock_quantity': random.randint(10, 100)
                    }
                )
                created_count += 1
                self.stdout.write(f"Created: {name} ({suffix})")

        self.stdout.write(self.style.SUCCESS(f'Successfully created {created_count} variants!'))