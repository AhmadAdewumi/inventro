from django.shortcuts import render, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .services import (get_product_by_barcode, process_purchase, adjust_inventory, 
                       get_dashboard_stats, get_top_selling_items, receive_purchase_order,
                       process_refund, create_product_and_variant, get_barcode_pdf_buffer,
                       create_purchase_order
                       )
from .serializers import (ProductVariantSerializer, PurchaseItemSerializer,
                          PurchaseSerializer, InventoryAdjustmentSerializer, 
                          SupplierSerializer, PurchaseOrderSerializer, 
                          PurchaseOrderItemSerializer, CreatePurchaseOrderSerializer,
                          RefundSerializer, OrderSerializer, InventoryLogSerializer)
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
import traceback
from .models import (Supplier, PurchaseOrder, PurchaseOrderItem, 
                     ProductVariant, Order, Product, ProductVariant,
                     InventoryLog
                     )
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from .utils import generate_barcode_pdf
import uuid

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


# Create your views here.
class ScanItemView(APIView):
    """
    Endpoint: GET /api/scan/<barcode>/
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, barcode):
        #-- we call the service method
        variant = get_product_by_barcode(barcode)

        if not variant:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        #-- serializing the object to json
        data = ProductVariantSerializer(variant).data

        return Response(data, status=status.HTTP_200_OK)
    

@method_decorator(csrf_exempt, name='dispatch')
class PurchaseView(APIView):
    authentication_classes = [BasicAuthentication] 
    permission_classes = [IsAuthenticated] 

    def post(self, request):
        serializer = PurchaseSerializer(data=request.data)
        if serializer.is_valid():
            try:
                order = process_purchase(
                    user=request.user, 
                    payment_method=serializer.validated_data['payment_method'], # Pass this
                    items_data=serializer.validated_data['items']
                )
                return Response(
                    {"message": "Success", "order_id": order.id, "total": order.total_amount}, 
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:

                print("!!!!!!!! ERROR TRACEBACK !!!!!!!!")
                print(traceback.format_exc()) 
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

@method_decorator(csrf_exempt, name='dispatch')
class InventoryAdjustmentView(APIView):
    authentication_classes = [BasicAuthentication] 
    permission_classes = [IsAuthenticated] 

    def post(self, request):
        serializer = InventoryAdjustmentSerializer(data = request.data)
        if serializer.is_valid():
            try:
                variant = adjust_inventory(request.user, serializer.validated_data)
                return Response({
                    "message" : "Stock Updated Successfully",
                    "sku" : variant.sku,
                    "new_quantity" : variant.stock_quantity
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    "error" : str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class DashboardStatView(APIView):
    authentication_classes = [BasicAuthentication] 
    permission_classes = [IsAuthenticated] 

    def get(self, request):
        stats = get_dashboard_stats()
        return Response(stats)
    
class TopSellingProductView(APIView):
    authentication_classes = [BasicAuthentication] 
    permission_classes = [IsAuthenticated] 

    def get(self, request):
        data = get_top_selling_items()
        return Response(data)
    
class SupplierListView(APIView):
    def get(self, request):
        suppliers = Supplier.objects.all()
        return Response(SupplierSerializer(suppliers, many = True).data)
    
    def post(self, request):
        serializer = SupplierSerializer(data = request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
@method_decorator(csrf_exempt, name='dispatch')
class PurchaseOrderView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
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
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, po_id): #-- po_id --> purchase order id
        try:
            receive_purchase_order(request.user, po_id)
            return Response({
                "message" : "Stock received successfully"
            })
        except Exception as e:
            return Response({
                "error" : str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class RefundView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated] 
    def post(self, request):
        serializer = RefundSerializer(data=request.data)
        if serializer.is_valid():
            try:
                result = process_refund(request.user, serializer.validated_data['order_id'], serializer.validated_data['items'])
                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                print(traceback.format_exc())
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class OrderListView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.select_related('cashier').prefetch_related('items__variant__product').order_by('-created_at')

        status_param = request.query_params.get('status')
        if status_param == 'refunded':
            #-- show orders that are explicitly 'refunded' OR have items with refunded qty > 0
            #-- this catches "Partial Refunds" that might still be marked 'completed'
            orders = orders.filter(Q(status='refunded') | Q(items__refunded_quantity__gt=0)).distinct()
        elif status_param == 'completed':
            orders = orders.filter(status='completed')
        elif status_param == 'pending':
            orders = orders.filter(status='pending')

        #-- if status is None or all, we return everything

        return Response(OrderSerializer(orders[:50], many=True).data)
    
class ProductListView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request): #-- search functionality
        query = request.query_params.get('search', '')
        variants = ProductVariant.objects.select_related('product').all().order_by('-stock_quantity')

        if query:
            variants = variants.filter(
                Q(product__name__icontains=query) |
                Q(sku__icontains=query) |
                Q(barcode__icontains=query)
            )

            #-- Pagination, limit to 50
        return Response(ProductVariantSerializer(variants[:50], many=True).data)
        
    
    #-- to create product and variants in a GO
    # -- expected json --> { name, category, price, cost, stock, barcode, sku }, description as an optional fields can be included    
    def post(self, request):
        try:
            variant = create_product_and_variant(request.data)
            return Response(ProductVariantSerializer(variant).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {
                    "error" : str(e)
                }, status= status.HTTP_400_BAD_REQUEST
            )
        
class PurchaseOrderListView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pos = PurchaseOrder.objects.select_related('supplier', 'created_by').order_by('-created_at')[:50]
        return Response(PurchaseOrderSerializer(pos, many = True).data)
    
class AuditLogView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]


    def get(self, request):
        logs = InventoryLog.objects.select_related('variant__product', 'user').order_by('-created_at')[:50]
        return Response(InventoryLogSerializer(logs, many=True).data)
    
class BarcodeGeneratorView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        category = request.query_params.get('category')
        ids_param = request.query_params.get('ids')
        
        variant_ids = None
        if ids_param:
            #-- converts "1,2,3" string into list [1, 2, 3]
            try:
                variant_ids = [int(x) for x in ids_param.split(',') if x.isdigit()] #-- list comprehension
            except ValueError:
                pass #-- ignores bad input

        pdf_buffer = get_barcode_pdf_buffer(category, variant_ids)

        filename = f"barcodes_{uuid.uuid4().hex[:6].upper()}.pdf"

        response = HttpResponse(pdf_buffer, content_type = 'application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
class PurchaseOrderListView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        pos = PurchaseOrder.objects.select_related('supplier', 'created_by').order_by('-created_at')[:50]
        return Response(PurchaseOrderSerializer(pos, many=True).data)
    
@login_required(login_url='login')
def store_os_view(request):
    return render(request, 'inventory/store_os.html')

def logout_view(request):
    logout(request)
    return redirect('login')
