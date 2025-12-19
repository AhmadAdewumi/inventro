import io
import traceback
import uuid

from django.contrib.auth.hashers import check_password
from django.utils import timezone
from os import name

from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Q, ProtectedError, Sum, Count
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (Supplier, PurchaseOrder, Order, ProductVariant,
                     InventoryLog, Customer, StocktakeSession, Notification, StoreSettings
                     )
from .permissions import IsManager
from .serializers import (ProductVariantSerializer, PurchaseSerializer, InventoryAdjustmentSerializer,
                          SupplierSerializer, PurchaseOrderSerializer,
                          CreatePurchaseOrderSerializer,
                          RefundSerializer, OrderSerializer, InventoryLogSerializer,
                          UserSerializer, CreateUserSerializer, CustomerSerializer, StocktakeSessionSerializer,
                          NotificationSerializer, StoreSettingsSerializer
                          )
from .services import (get_product_by_barcode, process_purchase, adjust_inventory,
                       get_dashboard_stats, get_top_selling_items, receive_purchase_order,
                       process_refund, create_product_and_variant, get_barcode_pdf_buffer,
                       create_purchase_order, start_stocktake, update_stocktake_item, approve_stocktake
                       )
from .utils import export_sales_csv, export_inventory_csv


# Create your views here.

class UserMetaView(APIView):
    """
    Returns role of current user to React
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "username": request.user.username,
            "is_manager": request.user.groups.filter(name='Manager').exists() or request.user.is_superuser,
            "is_superuser": request.user.is_superuser
        })


class ScanItemView(APIView):
    """
    Endpoint: GET /api/scan/<barcode>/
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, barcode):
        # -- we call the service method
        variant = get_product_by_barcode(barcode)

        if not variant:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # -- serializing the object to json
        data = ProductVariantSerializer(variant).data

        return Response(data, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class PurchaseView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PurchaseSerializer(data=request.data)
        if serializer.is_valid():
            try:
                order = process_purchase(
                    request.user,
                    serializer.validated_data['payment_method'],
                    serializer.validated_data['items'],
                    serializer.validated_data.get('customer_id'),
                    serializer.validated_data.get('is_quote', False)
                )
                msg = "Quote Created" if serializer.validated_data.get('is_quote') else "Success"
                return Response(
                    {"message": msg, "order_id": order.id, "total": order.total_amount},
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class InventoryAdjustmentView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InventoryAdjustmentSerializer(data=request.data)
        if serializer.is_valid():
            try:
                variant = adjust_inventory(request.user, serializer.validated_data)
                return Response({
                    "message": "Stock Updated Successfully",
                    "sku": variant.sku,
                    "new_quantity": variant.stock_quantity
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    "error": str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DashboardStatsView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = get_dashboard_stats()
        return Response(stats)


class TopSellingProductView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = get_top_selling_items()
        return Response(data)


class SupplierListView(APIView):
    def get(self, request):
        suppliers = Supplier.objects.all()
        return Response(SupplierSerializer(suppliers, many=True).data)

    def post(self, request):
        serializer = SupplierSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class PurchaseOrderView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreatePurchaseOrderSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # REFACTORED: Logic moved to service
                purchase_order = create_purchase_order(request.user, serializer.validated_data)
                return Response({"message": "PO Created", "id": purchase_order.id}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class ReceivePurchaseOrderView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, po_id):  # -- po_id --> purchase order id
        try:
            receive_purchase_order(request.user, po_id)
            return Response({
                "message": "Stock received successfully"
            })
        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class RefundView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RefundSerializer(data=request.data)
        if serializer.is_valid():
            try:
                result = process_refund(request.user, serializer.validated_data['order_id'],
                                        serializer.validated_data['items'])
                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                print(traceback.format_exc())
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrderListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.select_related('cashier').prefetch_related('items__variant__product').order_by(
            '-created_at')

        status_param = request.query_params.get('status')
        if status_param == 'refunded':
            # -- show orders that are explicitly 'refunded' OR have items with refunded qty > 0
            # -- this catches "Partial Refunds" that might still be marked 'completed'
            orders = orders.filter(Q(status='refunded') | Q(items__refunded_quantity__gt=0)).distinct()
        elif status_param == 'completed':
            orders = orders.filter(status='completed')
        elif status_param == 'pending':
            orders = orders.filter(status='pending')

        # -- if status is None or all, we return everything

        return Response(OrderSerializer(orders[:50], many=True).data)


class ProductListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):  # -- search functionality
        query = request.query_params.get('search', '')
        # Only show active items
        variants = ProductVariant.objects.select_related('product').filter(is_active=True).order_by('-stock_quantity')

        if query:
            variants = variants.filter(
                Q(product__name__icontains=query) |
                Q(sku__icontains=query) |
                Q(barcode__icontains=query)
            )

            # -- Pagination, limit to 50
        return Response(ProductVariantSerializer(variants[:50], many=True).data)

    # -- to create product and variants in a GO
    # -- expected json --> { name, category, price, cost, stock, barcode, sku }, description as an optional fields can be included
    def post(self, request):
        try:
            variant = create_product_and_variant(request.data)
            return Response(ProductVariantSerializer(variant).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {
                    "error": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class PurchaseOrderListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pos = PurchaseOrder.objects.select_related('supplier', 'created_by').order_by('-created_at')[:50]
        return Response(PurchaseOrderSerializer(pos, many=True).data)


class AuditLogView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        # Base Query
        logs = InventoryLog.objects.select_related('variant__product', 'user').order_by('-created_at')

        # 1. Search Filter
        search = request.query_params.get('search')
        if search:
            logs = logs.filter(
                Q(variant__product__name__icontains=search) |
                Q(variant__sku__icontains=search) |
                Q(user__username__icontains=search) |
                Q(action__icontains=search) |
                Q(note__icontains=search)
            )

        # 2. Date Filter
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date and end_date:
            logs = logs.filter(created_at__date__range=[start_date, end_date])

        # 3. Pagination Support
        paginator = PageNumberPagination()
        paginator.page_size = 20 # Backend chunks
        result_page = paginator.paginate_queryset(logs, request)
        serializer = InventoryLogSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)


class BarcodeGeneratorView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        category = request.query_params.get('category')
        ids_param = request.query_params.get('ids')

        variant_ids = None
        if ids_param:
            # -- converts "1,2,3" string into list [1, 2, 3]
            try:
                variant_ids = [int(x) for x in ids_param.split(',') if x.isdigit()]  # -- list comprehension
            except ValueError:
                pass  # -- ignores bad input

        pdf_buffer = get_barcode_pdf_buffer(category, variant_ids)

        filename = f"barcodes_{uuid.uuid4().hex[:6].upper()}.pdf"

        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PurchaseOrderListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pos = PurchaseOrder.objects.select_related('supplier', 'created_by').order_by('-created_at')[:50]
        return Response(PurchaseOrderSerializer(pos, many=True).data)


# ---------------
# STAFF MANAGEMENT
# ---------------
class StaffView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        users = User.objects.filter(is_superuser=False).order_by('-date_joined')
        return Response(UserSerializer(users, many=True).data)

    def post(self, request):
        serializer = CreateUserSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # .save() calls the create() method in the serializer
                serializer.save()
                return Response({"message": "Staff created successfully"}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StaffActionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            if user.is_superuser: return Response({"error": "Cannot edit owner"}, status=400)

            user.is_active = not user.is_active
            user.save()
            state = "Active" if user.is_active else "Inactive"
            return Response({"message": f"User is now {state}"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)


class ExportSalesView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        # Export all completed orders
        orders = Order.objects.filter(status='completed').select_related('cashier').order_by('-created_at')
        csv_data = export_sales_csv(orders)

        filename = f"sales_ledger_{uuid.uuid4().hex[:6].upper()}.csv"

        response = HttpResponse(csv_data, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ExportInventoryView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        variants = ProductVariant.objects.select_related('product').all()
        csv_data = export_inventory_csv(variants)

        filename = f"inventory_valuation_{uuid.uuid4().hex[:6].upper()}.csv"

        response = HttpResponse(csv_data, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class DatabaseBackupView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        # Uses Django's built-in dumpdata command
        buffer = io.StringIO()
        call_command('dumpdata', 'inventory', stdout=buffer)

        filename = f"backup_{uuid.uuid4().hex[:6].upper()}.json"

        response = HttpResponse(buffer.getvalue(), content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class CustomerView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]  # Cashiers can view/add customers

    def get(self, request):
        query = request.query_params.get('search', '')
        customers = Customer.objects.all().order_by('-created_at')
        if query:
            customers = customers.filter(
                Q(name__icontains=query) | Q(phone__icontains=query)
            )
        return Response(CustomerSerializer(customers[:50], many=True).data)

    def post(self, request):
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@login_required(login_url='login')
def receipt_view(request, order_id):
    try:
        order = Order.objects.select_related('cashier', 'customer').prefetch_related('items__variant__product').get(
            id=order_id)

        # Calculate Tax Breakdown logic
        # We need to loop through items to sum up the hidden tax parts
        total_tax = 0
        subtotal_ex_tax = 0

        for item in order.items.all():
            # Formula: Tax = Price - (Price / (1 + rate/100))
            # We use the variant's tax_rate stored at the time (Note: ideally OrderItem should freeze tax_rate too, but we'll use current for V1)
            rate = item.variant.tax_rate
            line_total = item.get_total()

            if rate > 0:
                # Example: 107.50 / 1.075 = 100.00
                ex_tax = line_total / (1 + (rate / 100))
                tax_amt = line_total - ex_tax
                total_tax += tax_amt
                subtotal_ex_tax += ex_tax
            else:
                subtotal_ex_tax += line_total

        settings, _ = StoreSettings.objects.get_or_create(id=1)
        context = {
            'order': order,
            'settings': settings,
            'total_tax': round(total_tax, 2),
            'subtotal': round(subtotal_ex_tax, 2)
        }
        return render(request, 'inventory/receipt.html', context)

    except Order.DoesNotExist:
        return HttpResponse("Order not found", status=404)


class StocktakeListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        sessions = StocktakeSession.objects.order_by('-created_at')[:20]
        return Response(StocktakeSessionSerializer(sessions, many=True).data)

    def post(self, request):
        # Start new session
        try:
            session = start_stocktake(request.user, request.data.get('note', ''))
            return Response({"message": "Stocktake Started", "id": session.id}, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class StocktakeDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request, pk):
        try:
            session = StocktakeSession.objects.prefetch_related('items__variant__product').get(id=pk)
            return Response(StocktakeSessionSerializer(session).data)
        except StocktakeSession.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

    def post(self, request, pk):
        # Update count for an item
        # Body: { barcode: "123", quantity: 50 }
        barcode = request.data.get('barcode')
        qty = request.data.get('quantity')
        try:
            update_stocktake_item(pk, barcode, qty)
            return Response({"message": "Count updated"})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    def put(self, request, pk):
        # Approve/Finalize Session
        try:
            approve_stocktake(request.user, pk)
            return Response({"message": "Stocktake Completed & Inventory Updated"})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    def delete(self, request, pk):
        try:
            session = StocktakeSession.objects.get(id=pk)

            if session.status == 'completed':
                return Response({
                    "error": "Cannot delete a completed stocktake. It is part of the permanent audit trail."
                }, status=400)

            session.delete()
            return Response({"message": "Stocktake session discarded successfully"})

        except StocktakeSession.DoesNotExist:
            return Response({"error": "Session not found"}, status=404)


# --- SETTINGS VIEW ---
class StoreSettingsView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get or create the singleton record
        settings, _ = StoreSettings.objects.get_or_create(id=1)
        return Response(StoreSettingsSerializer(settings).data)

    def post(self, request):
        if not (request.user.is_superuser or request.user.groups.filter(name='Manager').exists()):
            return Response({
                "error" : "Permission denied: Managers only"
            }, status = status.HTTP_403_FORBIDDEN)

        settings, _ = StoreSettings.objects.get_or_create(id=1)
        serializer = StoreSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


# --- NOTIFICATIONS VIEW ---
class NotificationView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]  # Cashiers can see alerts too? Maybe just managers.

    def get(self, request):
        # Unread notifications
        notifs = Notification.objects.filter(is_read=False).order_by('-created_at')
        return Response(NotificationSerializer(notifs, many=True).data)

    def put(self, request, pk):
        # Mark as read
        try:
            notif = Notification.objects.get(id=pk)
            notif.is_read = True
            notif.save()
            return Response({"status": "ok"})
        except Notification.DoesNotExist:
            return Response({"error": "Not found"}, status=404)


#-- DELETE QUOTES
class OrderDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            order = Order.objects.get(id=pk)
            # SAFETY CHECK: Only allow deleting Quotes or Pending orders (not Completed ones)
            if order.status == 'completed' or order.status == 'refunded':
                return Response({"error": "Cannot delete completed records. Use Refund instead."}, status=400)

            order.delete()  # Hard delete is okay for quotes/drafts
            return Response({"message": "Order/Quote deleted successfully"})
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)


#-- DELETE CUSTOMERS
class CustomerDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            customer = Customer.objects.get(id=pk)
            #-- Don't delete if they owe us money or have history
            if customer.orders.exists():
                return Response({"error": "Cannot delete customer with transaction history."}, status=400)

            customer.delete()
            return Response({"message": "Customer deleted"})
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found"}, status=404)


#-- DELETE SUPPLIERS
class SupplierDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            supplier = Supplier.objects.get(id=pk)
            #-- Don't delete if we have Purchase Orders from them
            if supplier.orders.exists():
                return Response({"error": "Cannot delete supplier with Purchase Orders."}, status=400)

            supplier.delete()
            return Response({"message": "Supplier deleted"})
        except Supplier.DoesNotExist:
            return Response({"error": "Supplier not found"}, status=404)

class ProductDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def delete(self, request, pk):
        try:
            variant = ProductVariant.objects.get(id=pk)
            #-- Soft Delete: We mark as inactive so history remains safe
            variant.is_active = False
            variant.save()
            return Response({"message": "Product deleted successfully"})
        except ProductVariant.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)


class StaffDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def delete(self, request, pk):
        try:
            user = User.objects.get(id=pk)

            #-- Protect the Owner
            if user.is_superuser:
                return Response({"error": "Cannot delete the Superuser/Owner."}, status=400)

            #-- Attempt Deletion
            user.delete()
            return Response({"message": "Staff deleted successfully"})

        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
        except ProtectedError:
            #-- Handle Foreign Key Constraints (Safety Net)
            return Response({
                "error": "Cannot delete staff member who has created orders or logs. Please deactivate them instead."
            }, status=400)

class SalesReportView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        # Default to today
        start_date = request.query_params.get('start', timezone.now().date())
        end_date = request.query_params.get('end', timezone.now().date())

        # Filter completed orders in range
        orders = Order.objects.filter(
            status='completed',
            created_at__date__range=[start_date, end_date]
        ).order_by('-created_at')

        # 1. Total Revenue
        total_revenue = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0

        # 2. Breakdown by Payment Method (Cash vs Card vs Transfer)
        method_breakdown = orders.values('payment_method').annotate(
            total=Sum('total_amount'),
            count=Count('id')
        )

        return Response({
            "total_revenue": total_revenue,
            "breakdown": method_breakdown,
            "orders": OrderSerializer(orders, many=True).data
        })


def setup_view(request):
    """
    Redirects here if no users exist. Allows creating the Owner account.
    """
    if User.objects.exists():
        return redirect('login')  # Security: Block access if owner exists

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        store_name = request.POST.get('store_name')

        if not username or not password:
            return render(request, 'inventory/setup.html', {'error': 'All fields required'})

        # Create Superuser
        User.objects.create_superuser(username=username, password=password)

        # Create Default Settings
        settings, _ = StoreSettings.objects.get_or_create(id=1)
        if store_name:
            settings.store_name = store_name
            settings.save()

        return redirect('login')

    return render(request, 'inventory/setup.html')


class ChangePasswordView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        user = request.user

        if not check_password(old_password, user.password):
            return Response({"error": "Current password is incorrect"}, status=400)

        user.set_password(new_password)
        user.save()

        # Keep user logged in after password change
        update_session_auth_hash(request, user)

        return Response({"message": "Password updated successfully"})

@login_required(login_url='login')
def store_os_view(request):
    return render(request, 'inventory/store_os.html')


def logout_view(request):
    logout(request)
    return redirect('login')
