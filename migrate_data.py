from NCDNEXT_SQLIFE import app, db, Customer, OrderItem, MenuCategory, MenuItem
import json
from datetime import datetime

def migrate():
    print("=======================================")
    print("STARTING MIGRATION PROCESS...")
    
    # 1. ย้ายข้อมูลเมนู
    print("\n[1/2] Migrating menu data...")
    try:
        with open('menu_config.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        print(f"  - Found {len(menu_data)} categories in menu_config.json")
        
        for category_name, items in menu_data.items():
            category_obj = MenuCategory.query.filter_by(name=category_name).first()
            if not category_obj:
                category_obj = MenuCategory(name=category_name)
                db.session.add(category_obj)
            
            for item_name in items:
                item_obj = MenuItem.query.filter_by(name=item_name, category=category_obj).first()
                if not item_obj:
                    new_item = MenuItem(name=item_name, category=category_obj)
                    db.session.add(new_item)
        db.session.commit()
        print("  - Menu migration successful!")
    except Exception as e:
        print(f"  - [ERROR] Error migrating menu: {e}")
        db.session.rollback()

    # 2. ย้ายข้อมูลลูกค้า
    print("\n[2/2] Migrating customer data...")
    try:
        with open('customer_data.json', 'r', encoding='utf-8') as f:
            customer_data = json.load(f)
        print(f"  - Found {len(customer_data)} customer records in customer_data.json")
        
        print("  - Clearing old data from database tables (Customer, OrderItem)...")
        OrderItem.query.delete()
        Customer.query.delete()
        db.session.commit()
        print("  - Old database records cleared.")

        added_count = 0
        for record in customer_data:
            new_customer = Customer(
                name=record.get('name'),
                phone=record.get('phone', ''),
                order_method=record.get('order_method', ''),
                order_total=record.get('order_total', 0.0),
                date=datetime.strptime(record.get('date'), '%Y-%m-%d').date()
            )
            for item_str in record.get('ordered_items', []):
                order_item = OrderItem(item_string=item_str)
                new_customer.items.append(order_item)
            
            db.session.add(new_customer)
            added_count += 1
        
        db.session.commit()
        print(f"  - Successfully added {added_count} new customer records to database.")
        print("  - Customer data migration successful!")
    except Exception as e:
        print(f"  - [ERROR] Error migrating customers: {e}")
        db.session.rollback()
    
    print("\n...MIGRATION FINISHED.")
    print("=======================================")

if __name__ == '__main__':
    # เปลี่ยนชื่อไฟล์ให้ตรงกับของคุณ
    from NCDNEXT_SQLIFE import app 
    with app.app_context():
        migrate()