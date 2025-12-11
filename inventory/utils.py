import csv
import io

from reportlab.graphics.barcode import code128  # -- standard for product labels
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


# Note: We removed 'Drawing' and 'renderPDF' imports as they caused the crash

def generate_barcode_pdf(variants):
    """
    Generates a PDF buffer containing barcode labels.
    Layout: 3 columns x 7 rows (21 labels per page).
    """
    buffer = io.BytesIO() #-- we build the pdf entirely in memory
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Label Dimensions (Avery Standard) #-- we are using 3 columns and 7 rows per page  
    label_width = 70 * mm
    label_height = 37 * mm
    margin_x = 5 * mm
    margin_y = 10 * mm
    
    #-- this keep tracks of where the next label will be drawn
    col = 0 
    row = 0
    
    for variant in variants:
        # Calculate X/Y position
        x = margin_x + (col * label_width)
        # PDF coordinates start from bottom-left, so we calculate "up from bottom"
        y = height - margin_y - ((row + 1) * label_height) 
        
        # 1. Create Barcode Object
        #-- We ensure the barcode data is a string to avoid errors
        code_data = str(variant.barcode)
        barcode = code128.Code128(code_data, barHeight=10*mm, barWidth=1.2) #-- bar width controls thickness
        
        # We shift it slightly (10mm right, 5mm up) inside the label box to keep it nicely positioned and spaced well
        barcode.drawOn(p, x + 10*mm, y + 5*mm)
        
        # 3. Draw Text Details
        p.setFont("Helvetica-Bold", 10)
        p.drawString(x + 5*mm, y + 25*mm, variant.product.name[:20]) #-- this draws the product name, and truncate long names
        
        p.setFont("Helvetica", 8)
        p.drawString(x + 5*mm, y + 21*mm, f"Price: ${variant.price}") #-- for the price
        p.drawString(x + 5*mm, y + 2*mm, f"SKU: {variant.sku}") #-- for the sku
        
        # Grid Logic, once 3 columsns is filled, move to next row
        col += 1
        if col >= 3:
            col = 0
            row += 1
            
        # New Page if full (7 rows per page)
        if row >= 7:
            p.showPage()
            col = 0
            row = 0

    p.save() #-- finalizes the pdf and writes to buffer (in memory)
    buffer.seek(0) #-- moves the pointer to the start of the PDF , so django don't start reading from the end of file and won't see anything
    return buffer #-- give  it back to django

def export_sales_csv(orders):
    """
    Generates a CSV of sales for accounting.
    Columns: Date, Order ID, Cashier, Method, Total, Status
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Date', 'Order ID', 'Cashier', 'Payment Method', 'Total', 'Status'])
    
    for order in orders:
        writer.writerow([
            order.created_at.strftime("%Y-%m-%d %H:%M"),
            order.id,
            order.cashier.username,
            order.payment_method,
            order.total_amount,
            order.status
        ])
    
    return buffer.getvalue()

def export_inventory_csv(variants):
    """
    Generates a CSV of current stock value.
    Columns: SKU, Product, Stock, Cost Price, Selling Price, Total Asset Value
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['SKU', 'Product', 'Stock', 'Cost Price', 'Selling Price', 'Total Asset Value'])
    
    for v in variants:
        asset_value = v.stock_quantity * v.cost_price
        writer.writerow([
            v.sku,
            v.product.name + ' ' + v.name_suffix,
            v.stock_quantity,
            v.cost_price,
            v.price,
            asset_value
        ])
        
    return buffer.getvalue()