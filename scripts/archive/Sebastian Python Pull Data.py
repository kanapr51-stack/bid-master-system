import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

DEBUG_PORT = 9222

def main():
    print("กำลังเชื่อมต่อกับ Chrome ...")

    with sync_playwright() as p:

        browser = None
        for attempt in range(15):
            try:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
                print("✅ เชื่อมต่อสำเร็จ!")
                break
            except Exception:
                print(f"  รอ... ({attempt+1}/15)")
                time.sleep(2)

        if not browser:
            print("❌ เชื่อมต่อไม่ได้")
            return

        context = browser.contexts[0]

        # ซ่อน automation signals ก่อนเปิดหน้าใดๆ
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
        """)

        page = context.new_page()

        # ดัก network requests เพื่อ debug
        redirects = []
        page.on("response", lambda r: redirects.append(f"{r.status} {r.url[:80]}") if r.status in [301,302,303,307,308] else None)

        print("\nStep 1: เปิด homepage ...")
        page.goto("https://www.gprocurement.go.th/homepage.html",
                  wait_until="networkidle", timeout=30000)

        # ตรวจ navigator.webdriver
        wd = page.evaluate("navigator.webdriver")
        print(f"  navigator.webdriver = {wd}")

        # ตรวจข้อมูลปุ่ม
        btn_info = page.evaluate("""() => {
            const b = document.querySelector('.login-button');
            return b ? {href: b.href, target: b.target, onclick: b.getAttribute('onclick')} : null;
        }""")
        print(f"  ปุ่ม info: {btn_info}")

        print("\nStep 2: คลิกปุ่มด้วย JavaScript ...")
        page.evaluate("document.querySelector('.login-button').click()")
        time.sleep(5)

        print(f"  URL หลังคลิก JS: {page.url}")
        print(f"  Redirects ที่เจอ: {redirects}")

        if "new_index" not in page.url:
            print("\nลอง navigate ด้วย page.goto ...")
            if btn_info and btn_info.get('href'):
                page.goto(btn_info['href'], wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                print(f"  URL: {page.url}")

        print(f"\nURL สุดท้าย: {page.url}")
        page.screenshot(path="debug_final.png")

        if "new_index" in page.url:
            print("\n✅ สำเร็จ!")
        else:
            print(f"\n❌ ยังเข้าไม่ได้")
            print(f"Redirects: {redirects}")

        input("\nกด Enter เพื่อปิด")
        browser.close()

if __name__ == "__main__":
    main()
