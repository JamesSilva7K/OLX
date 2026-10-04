import re

with open(r'd:\OLPG\app.py', 'r', encoding='utf8') as f:
    txt = f.read()

txt = txt.replace(
    'seller_avatar=(custom_item.get("seller_avatar") if custom_item and custom_item.get("seller_avatar") else cfgs.get("seller_avatar", "")),',
    '''seller_avatar=(custom_item.get("seller_avatar") if custom_item and custom_item.get("seller_avatar") else cfgs.get("seller_avatar", "")),
            seller_sales_completed=custom_item.get("seller_sales_completed", "") if custom_item else "",
            seller_sales_canceled=custom_item.get("seller_sales_canceled", "") if custom_item else "",
            seller_dispatch_time=custom_item.get("seller_dispatch_time", "") if custom_item else "",
            seller_rating=custom_item.get("seller_rating", "") if custom_item else "",
            seller_reviews=custom_item.get("seller_reviews", "") if custom_item else "",
            seller_level=custom_item.get("seller_level", "") if custom_item else "",
            seller_email_verified=custom_item.get("seller_email_verified", 1) if custom_item else 1,
            seller_phone_verified=custom_item.get("seller_phone_verified", 1) if custom_item else 1,
            seller_id_verified=custom_item.get("seller_id_verified", 1) if custom_item else 1,
            seller_fb_verified=custom_item.get("seller_fb_verified", 0) if custom_item else 0,
            seller_fb_url=custom_item.get("seller_fb_url", "") if custom_item else "",'''
)

with open(r'd:\OLPG\app.py', 'w', encoding='utf8') as f:
    f.write(txt)
