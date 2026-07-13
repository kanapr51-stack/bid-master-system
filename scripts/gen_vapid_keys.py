"""สร้าง VAPID key pair ครั้งเดียว — print ออก stdout เท่านั้น (ห้าม write ไฟล์/commit key)"""
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from py_vapid.utils import b64urlencode

v = Vapid02()
v.generate_keys()
priv = b64urlencode(
    v.private_key.private_numbers().private_value.to_bytes(32, "big"))
pub = b64urlencode(
    v.public_key.public_bytes(serialization.Encoding.X962,
                              serialization.PublicFormat.UncompressedPoint))
print("VAPID_PRIVATE_KEY=" + priv)
print("VAPID_SUBJECT=mailto:kanapr51@gmail.com")
print("NEXT_PUBLIC_VAPID_PUBLIC_KEY=" + pub)
