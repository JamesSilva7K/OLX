with open(r'd:\OLPG\app.py', 'r', encoding='utf8') as f:
    txt = f.read()

# 1. Read product_published_at from POST data
txt = txt.replace(
    'seller_fb_url = data.get("seller_fb_url", "").strip()',
    'seller_fb_url = data.get("seller_fb_url", "").strip()\n        product_published_at = data.get("product_published_at", "").strip()'
)

# 2. Pass to create_tenant_product
txt = txt.replace(
    'seller_fb_url=seller_fb_url\n            )',
    'seller_fb_url=seller_fb_url,\n                product_published_at=product_published_at\n            )'
)

# 3. Pass to render_template for /p/ route
txt = txt.replace(
    'seller_fb_url=custom_item.get("seller_fb_url", "") if custom_item else "",',
    'seller_fb_url=custom_item.get("seller_fb_url", "") if custom_item else "",\n            product_published_at=custom_item.get("product_published_at", "") if custom_item else "",'
)

with open(r'd:\OLPG\app.py', 'w', encoding='utf8') as f:
    f.write(txt)
print("Done")
