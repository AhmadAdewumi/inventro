from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from inventory.models import Order, ProductVariant, InventoryLog

class Command(BaseCommand):
    help = 'Sets up Cashier and Manager groups with default permissions'

    def handle(self, *args, **options):
        #-- we ceate the groups 
        cashier_group, _ = Group.objects.get_or_create(name='Cashier')
        manager_group, _ = Group.objects.get_or_create(name = 'Manager')

        self.stdout.write(self.style.SUCCESS('Successfully created Cashier and Manager groups!'))