import re

with open(r'd:\OLPG\app.py', 'r', encoding='utf8') as f:
    txt = f.read()

txt = txt.replace(
    'breadcrumb_zone = data.get("breadcrumb_zone", "").strip()',
    '''breadcrumb_zone = data.get("breadcrumb_zone", "").strip()
        seller_sales_completed = data.get("seller_sales_completed", "").strip()
        seller_sales_canceled = data.get("seller_sales_canceled", "").strip()
        seller_dispatch_time = data.get("seller_dispatch_time", "").strip()
        seller_rating = data.get("seller_rating", "").strip()
        seller_reviews = data.get("seller_reviews", "").strip()
        seller_level = data.get("seller_level", "").strip()
        seller_email_verified = 1 if data.get("seller_email_verified", 1) in (1, "1", True, "true") else 0
        seller_phone_verified = 1 if data.get("seller_phone_verified", 1) in (1, "1", True, "true") else 0
        seller_id_verified = 1 if data.get("seller_id_verified", 1) in (1, "1", True, "true") else 0
        seller_fb_verified = 1 if data.get("seller_fb_verified", 0) in (1, "1", True, "true") else 0
        seller_fb_url = data.get("seller_fb_url", "").strip()'''
)

txt = txt.replace(
    'breadcrumb_zone=breadcrumb_zone\n            )',
    '''breadcrumb_zone=breadcrumb_zone,
                seller_sales_completed=seller_sales_completed,
                seller_sales_canceled=seller_sales_canceled,
                seller_dispatch_time=seller_dispatch_time,
                seller_rating=seller_rating,
                seller_reviews=seller_reviews,
                seller_level=seller_level,
                seller_email_verified=seller_email_verified,
                seller_phone_verified=seller_phone_verified,
                seller_id_verified=seller_id_verified,
                seller_fb_verified=seller_fb_verified,
                seller_fb_url=seller_fb_url
            )'''
)

with open(r'd:\OLPG\app.py', 'w', encoding='utf8') as f:
    f.write(txt)
