import re

with open(r'd:\OLPG\tg_webhook.py', 'r', encoding='utf8') as f:
    txt = f.read()

# Update create_tenant_product definition
txt = re.sub(
    r'(def create_tenant_product.*?det_color="", payment_badges="", breadcrumb_zone="")(:)',
    r'\1, seller_sales_completed="", seller_sales_canceled="", seller_dispatch_time="", seller_rating="", seller_reviews="", seller_level="", seller_email_verified=1, seller_phone_verified=1, seller_id_verified=1, seller_fb_verified=0, seller_fb_url=""\2',
    txt, flags=re.DOTALL
)

# Update INSERT INTO
txt = txt.replace(
    'det_color, payment_badges, breadcrumb_zone, created_at)',
    'det_color, payment_badges, breadcrumb_zone, created_at, seller_sales_completed, seller_sales_canceled, seller_dispatch_time, seller_rating, seller_reviews, seller_level, seller_email_verified, seller_phone_verified, seller_id_verified, seller_fb_verified, seller_fb_url)'
)
txt = txt.replace(
    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)' # 28 + 11 = 39
)
txt = txt.replace(
    'det_memory, det_color, payment_badges, breadcrumb_zone or "", time.time()))',
    'det_memory, det_color, payment_badges, breadcrumb_zone or "", time.time(), seller_sales_completed, seller_sales_canceled, seller_dispatch_time, seller_rating, seller_reviews, seller_level, seller_email_verified, seller_phone_verified, seller_id_verified, seller_fb_verified, seller_fb_url))'
)

# Update get_tenant_products and get_product_by_code
txt = txt.replace(
    "COALESCE(breadcrumb_zone, '') AS breadcrumb_zone,",
    "COALESCE(breadcrumb_zone, '') AS breadcrumb_zone, COALESCE(seller_sales_completed, '') AS seller_sales_completed, COALESCE(seller_sales_canceled, '') AS seller_sales_canceled, COALESCE(seller_dispatch_time, '') AS seller_dispatch_time, COALESCE(seller_rating, '') AS seller_rating, COALESCE(seller_reviews, '') AS seller_reviews, COALESCE(seller_level, '') AS seller_level, COALESCE(seller_email_verified, 1) AS seller_email_verified, COALESCE(seller_phone_verified, 1) AS seller_phone_verified, COALESCE(seller_id_verified, 1) AS seller_id_verified, COALESCE(seller_fb_verified, 0) AS seller_fb_verified, COALESCE(seller_fb_url, '') AS seller_fb_url,"
)

# Update update_tenant_product ALLOWED
txt = txt.replace(
    '"payment_badges", "breadcrumb_zone"}',
    '"payment_badges", "breadcrumb_zone", "seller_sales_completed", "seller_sales_canceled", "seller_dispatch_time", "seller_rating", "seller_reviews", "seller_level", "seller_email_verified", "seller_phone_verified", "seller_id_verified", "seller_fb_verified", "seller_fb_url"}'
)

txt = txt.replace(
    'if k in ("coupon_active", "coupon_only_shipping"):',
    'if k in ("coupon_active", "coupon_only_shipping", "seller_email_verified", "seller_phone_verified", "seller_id_verified", "seller_fb_verified"):'
)

with open(r'd:\OLPG\tg_webhook.py', 'w', encoding='utf8') as f:
    f.write(txt)
