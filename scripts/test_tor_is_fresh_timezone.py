"""test_tor_is_fresh_timezone.py — job_matcher.tor_is_fresh(today=None) ต้องใช้วันที่ไทย
(+07:00) ไม่ใช่ system local date. บั๊กเดิม: VPS system tz=UTC → ช่วง 17:00-23:59 UTC
(=00:00-06:59 น. ไทย) วันที่ไทย "ล้ำหน้า" UTC 1 วัน → date.today() (UTC) ให้ diff ติดลบ →
fresh=False ผิด ทั้งที่งานเพิ่งประกาศวันนี้จริง (เจอจาก test_portal_discover_api.py fail บน
VPS 2026-07-21, ตอนนั้น UTC=19:37 20-07 / ไทย=02:37 21-07).
"""
import os, sys, datetime as dt
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import job_matcher as jm  # noqa: E402

# จำลอง VPS: system clock UTC = 2026-07-20 19:37 (ยังเป็นเมื่อวานใน UTC)
# แต่เวลาไทย (+07:00) = 2026-07-21 02:37 (เป็นวันนี้แล้วในไทย)
_FAKE_UTC_NOW = dt.datetime(2026, 7, 20, 19, 37, 0)


class _FakeDatetime(dt.datetime):
    """system-local now()/today() = UTC เสมอ (จำลอง VPS ที่ OS timezone=UTC ไม่ว่าเครื่อง
    รัน test จริงจะตั้ง timezone อะไรก็ตาม — ถ้า mock แค่ .now() เฉยๆ โค้ดเก่าที่เรียก
    date.today() ตรงจะไม่โดน mock เลย แล้ว test จะไม่ discriminate อะไร (พลาดรอบแรก)."""
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return _FAKE_UTC_NOW
        return _FAKE_UTC_NOW.replace(tzinfo=dt.timezone.utc).astimezone(tz)


class _FakeDate(dt.date):
    @classmethod
    def today(cls):
        return _FAKE_UTC_NOW.date()  # โค้ดเก่า: date.today() = system UTC date ตรงๆ


def test_default_today_uses_thai_tz_not_system_utc():
    with patch("datetime.datetime", _FakeDatetime), patch("datetime.date", _FakeDate):
        # announce_date = วันนี้ตามเวลาไทย (2026-07-21) ขณะ system UTC ยังเป็น 2026-07-20
        assert jm.tor_is_fresh("2026-07-21", days=14) is True, \
            "งานประกาศ 'วันนี้ตามเวลาไทย' ต้อง fresh=True แม้ system UTC ยังเป็นเมื่อวาน"
        # เมื่อวานตามเวลาไทย (2026-07-20) ก็ยังต้อง fresh (อยู่ในช่วง 14 วัน)
        assert jm.tor_is_fresh("2026-07-20", days=14) is True


def test_explicit_today_unaffected():
    """caller ที่ inject today เอง (เช่น test_job_matcher.py เดิม) ต้องไม่เปลี่ยนพฤติกรรม"""
    fixed_today = dt.date(2026, 6, 6)
    assert jm.tor_is_fresh("2026-06-06", fixed_today, days=14) is True
    assert not jm.tor_is_fresh("2026-05-20", fixed_today, days=14)


test_default_today_uses_thai_tz_not_system_utc()
test_explicit_today_unaffected()
print("PASS test_tor_is_fresh_timezone")
