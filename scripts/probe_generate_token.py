"""
Proof of concept: Generate X-Announcement-Token programmatically.

Reverse-engineered from egp-aann09-web chunk 594:
  generateAnnouncementKey(projectId):
    m = encryptData({projectId})
    return encryptData(m)

  encryptData(obj):
    return encodeURIComponent(CryptoJS.AES.encrypt(JSON.stringify(obj), "RDCrypto").toString())

  CryptoJS.AES uses EVP_BytesToKey (MD5) for passphrase → key derivation (OpenSSL-compatible)
"""
import json
import hashlib
import base64
import os
import urllib.parse
import struct
import requests

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


PASSPHRASE = "RDCrypto"
BASE_URL = "https://process5.gprocurement.go.th"
GENERATE_TOKEN_URL = BASE_URL + "/egp-atpj27-service/pb/a-egp-allt-project/announcement/generateToken"

HEADERS_NO_AUTH = {
    "Content-Type": "application/json",
    "noToken": "noToken",
    "noDataProfile": "noDataProfile",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0",
    "Referer": "https://process5.gprocurement.go.th/",
    "Origin": "https://process5.gprocurement.go.th",
}


def evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16) -> tuple[bytes, bytes]:
    """OpenSSL EVP_BytesToKey with MD5 (CryptoJS default)."""
    d = b""
    d_i = b""
    while len(d) < key_len + iv_len:
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:key_len], d[key_len:key_len + iv_len]


def crypto_js_encrypt(plain_text: str, passphrase: str = PASSPHRASE) -> str:
    """
    Replicates CryptoJS.AES.encrypt(plainText, passphrase).toString()
    Output: base64("Salted__" + salt + ciphertext)
    """
    salt = os.urandom(8)
    key, iv = evp_bytes_to_key(passphrase.encode("utf-8"), salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plain_text.encode("utf-8"), AES.block_size))
    # OpenSSL format: "Salted__" + salt + ciphertext
    salted = b"Salted__" + salt + encrypted
    return base64.b64encode(salted).decode("utf-8")


def encrypt_data(obj) -> str:
    """
    Replicates CryptoLib.encryptData(obj):
      encodeURIComponent(CryptoJS.AES.encrypt(JSON.stringify(obj), "RDCrypto").toString())
    """
    json_str = json.dumps(obj, separators=(",", ":"))
    encrypted_b64 = crypto_js_encrypt(json_str)
    return urllib.parse.quote(encrypted_b64, safe="")


def generate_announcement_key(project_id: str) -> str:
    """
    Replicates EgpAnnouncementService.generateAnnouncementKey(projectId):
      const m = this.cryptoLib.encryptData({projectId: a});
      return this.cryptoLib.encryptData(m);
    """
    m = encrypt_data({"projectId": project_id})
    return encrypt_data(m)


def get_announcement_token(project_id: str) -> dict:
    """Full flow: key → POST generateToken → token"""
    key = generate_announcement_key(project_id)
    print(f"[key] length={len(key)}")
    print(f"[key] first 100: {key[:100]}")

    payload = {"key": key}
    print(f"\n[POST] {GENERATE_TOKEN_URL}")
    r = requests.post(GENERATE_TOKEN_URL, json=payload, headers=HEADERS_NO_AUTH, timeout=15)
    print(f"[resp] status={r.status_code}")
    print(f"[resp] body={r.text[:500]}")
    return {"status": r.status_code, "body": r.text}


def test_announcement_api_with_token(project_id: str, token: str):
    """Test if token works with the announcement API."""
    url = BASE_URL + "/egp-atpj27-service/pb/a-egp-allt-project/announcement"
    headers = {
        **HEADERS_NO_AUTH,
        "X-Announcement-Token": token,
    }
    params = {"projectId": project_id}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    print(f"\n[test API] status={r.status_code}")
    print(f"[test API] body={r.text[:300]}")


if __name__ == "__main__":
    # Test with a known project ID
    TEST_PROJECT_ID = "66099000032"  # from hardcoded value found in chunk 744
    print(f"Testing with projectId: {TEST_PROJECT_ID}")
    print("="*60)
    result = get_announcement_token(TEST_PROJECT_ID)

    # If successful, test the API
    if result["status"] == 200:
        try:
            data = json.loads(result["body"])
            token = data.get("data", "")
            if token:
                print(f"\n[token] {token[:80]}...")
                test_announcement_api_with_token(TEST_PROJECT_ID, token)
        except Exception as e:
            print(f"Parse error: {e}")
