"""로컬 데모 UI 회귀 검사. 실행 중인 Vite preview와 Playwright가 필요하다.

TIMEPICK_UI_URL=http://localhost:4173 python frontend/tests/ui_smoke.py
Windows: PLAYWRIGHT_CHANNEL=msedge. 운영 도메인과 운영 DB에는 접근하지 않는다.
"""
import os
import re
import unittest
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("TIMEPICK_UI_URL", "http://127.0.0.1:4173")
if urlparse(BASE).hostname not in {"localhost", "127.0.0.1"}:
    raise RuntimeError("UI 검사는 로컬 preview에서만 실행하세요.")


class PlatformUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(
            headless=True, channel=os.getenv("PLAYWRIGHT_CHANNEL") or None,
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(BASE)
        expect(self.page.get_by_role("heading", name="가격을 비교하고,\n살 때를 발견하세요.")).to_be_visible()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def test_theme_and_language_preferences(self):
        """다크/라이트 전환은 즉시 적용·저장되고, 영어 전환 후 메뉴가 영어로 보이며 한국어로 돌아올 수 있다"""
        self.page.get_by_role("button", name=re.compile("모드로 전환")).first.click()
        first = self.page.evaluate("document.documentElement.dataset.theme")
        self.page.reload()
        self.assertEqual(self.page.evaluate("document.documentElement.dataset.theme"), first)
        self.page.get_by_role("button", name="English로 보기").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(self.page.evaluate("document.documentElement.lang"), "en")
        expect(self.page.get_by_role("navigation", name="Main menu").get_by_role("link", name=re.compile("Compare prices"))).to_be_visible()
        self.page.get_by_role("button", name="한국어로 보기").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(self.page.evaluate("document.documentElement.lang"), "ko")
        self.assertEqual(self.errors, [])

    def test_search_and_price_range(self):
        p = self.page
        p.get_by_role("search", name="메인 상품 검색").get_by_role("searchbox").fill("이어폰")
        p.get_by_role("search", name="메인 상품 검색").get_by_role("button", name="가격 검색").click()
        expect(p.get_by_role("heading", name="상품 탐색")).to_be_visible()
        expect(p.get_by_role("heading", name="무선 이어폰 X2", exact=True)).to_be_visible()
        p.get_by_role("heading", name="무선 이어폰 X2", exact=True).click()
        expect(p.get_by_role("heading", name="쇼핑몰별 실구매가")).to_be_visible()
        for days in (7, 30, 90):
            p.get_by_role("button", name=f"{days}일", exact=True).click()
            expect(p.get_by_role("img", name="가격 변동 차트")).to_be_visible()
        expect(p.get_by_role("button", name="120일", exact=True)).to_have_count(0)
        expect(p.get_by_role("list", name="주요 사양").get_by_role("listitem").first).to_have_text("커널형")
        # 데모 모드 상품 사진은 Unsplash 참고 이미지이며 출처를 표시한다
        expect(p.locator('img[src^="https://images.unsplash.com/"][alt="무선 이어폰 X2"]').first).to_be_visible()
        expect(p.get_by_text("참고 이미지 · Unsplash").first).to_be_visible()

    def test_daily_goods_show_offline_kca_price(self):
        """생필품 상세에는 참가격(오프라인 판매점 조사 최저가)과 조사일이 함께 보인다. 디지털 상품에는 없다"""
        p = self.page
        p.goto(BASE + "/product/8")
        expect(p.get_by_text("오프라인 최저가 (참가격)")).to_be_visible()
        expect(p.get_by_text(re.compile(r"대형마트 · \d{4}-\d{2}-\d{2} 조사"))).to_be_visible()
        p.goto(BASE + "/product/1")
        expect(p.get_by_role("heading", name="무선 이어폰 X2")).to_be_visible()
        expect(p.get_by_text("오프라인 최저가 (참가격)")).to_have_count(0)

    def test_search_pages_keep_all_products(self):
        """상품 탐색은 서버(데모: mock) 페이지 단위로 받는다. 한 페이지보다 적으면 페이지 이동 버튼이 없다"""
        p = self.page
        p.goto(BASE + "/search")
        expect(p.get_by_role("heading", name="무선 이어폰 X2", exact=True)).to_be_visible()
        expect(p.get_by_role("navigation", name="검색 결과 페이지")).to_have_count(0)
        p.get_by_label("지금 구매 추천만").check()
        expect(p.get_by_text("검색 결과").first).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_watch_modal_and_keyboard(self):
        p = self.page
        p.goto(BASE + "/product/3")
        p.get_by_role("button", name="목표가 알림", exact=True).first.click()
        dialog = p.get_by_role("dialog")
        expect(dialog).to_be_visible()
        for _ in range(12):
            p.keyboard.press("Tab")
            self.assertTrue(p.evaluate("document.querySelector('dialog').contains(document.activeElement)"))
        dialog.get_by_label("목표 가격 (원)").fill("0")
        dialog.get_by_role("button", name="알림 저장").click()
        self.assertFalse(dialog.get_by_label("목표 가격 (원)").evaluate("(e) => e.validity.valid"))
        dialog.get_by_label("목표 가격 (원)").fill("999000")
        dialog.get_by_role("button", name="알림 저장").click()
        expect(dialog.get_by_text("목표가 알림이 저장되었습니다.")).to_be_visible()
        p.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(p.get_by_role("button", name="목표가 알림", exact=True).first).to_be_focused()
        p.goto(BASE + "/watchlist")
        expect(p.get_by_text("999,000원", exact=True)).to_be_visible()

    def test_signup_steps(self):
        p = self.page
        p.goto(BASE + "/signup")
        expect(p.get_by_role("button", name="동의하고 계속")).to_be_disabled()
        p.get_by_label("서비스 이용 안내에 동의합니다 (필수)").check()
        p.get_by_label("개인정보 처리 안내에 동의합니다 (필수)").check()
        p.get_by_role("button", name="동의하고 계속").click()
        p.get_by_label("이름", exact=True).fill("테스트 회원")
        p.get_by_label("이메일", exact=True).fill("ui-smoke@example.com")
        p.get_by_label("비밀번호", exact=True).fill("SafePass!2026")
        p.get_by_label("비밀번호 확인", exact=True).fill("mismatch")
        expect(p.get_by_role("button", name="가입 완료하기")).to_be_disabled()
        p.get_by_label("비밀번호 확인", exact=True).fill("SafePass!2026")
        p.get_by_role("button", name="디지털", exact=True).click()
        p.get_by_role("button", name="가입 완료하기").click()
        expect(p.get_by_role("heading", name="첫 알림을 설정해 볼까요?")).to_be_visible()
        expect(p.get_by_role("main").get_by_text("디지털", exact=True)).to_be_visible()
        p.get_by_role("button", name="목표가 알림", exact=True).first.click()
        p.get_by_role("dialog").get_by_role("button", name="알림 저장").click()
        expect(p.get_by_role("dialog").get_by_text("목표가 알림이 저장되었습니다.")).to_be_visible()
        p.get_by_role("dialog").get_by_role("button", name="확인", exact=True).click()
        expect(p.get_by_role("heading", name="가입과 알림 설정을 마쳤어요.")).to_be_visible()
        p.get_by_role("link", name="다른 상품 둘러보기").click()
        p.get_by_label("내 관심 카테고리").check()
        expect(p.get_by_role("heading", name="세탁세제 3L")).to_have_count(0)

    def test_mobile_drawer_and_layout(self):
        p = self.page
        p.set_viewport_size({"width": 375, "height": 812})
        p.get_by_role("button", name="메뉴 열기").click()
        expect(p.get_by_role("dialog", name="메뉴")).to_be_visible()
        p.keyboard.press("Escape")
        expect(p.get_by_role("dialog", name="메뉴")).not_to_be_visible()
        self.assertTrue(p.evaluate("document.documentElement.scrollWidth <= innerWidth"))

    def test_login_protection_and_admin(self):
        p = self.page
        p.get_by_role("button", name="로그아웃", exact=True).click()
        p.get_by_role("navigation", name="주 메뉴").get_by_role("link", name="관심 상품").click()
        expect(p).to_have_url(re.compile(r"/login\?next="))
        p.get_by_role("button", name="일반 사용자 테스트").click()
        expect(p.get_by_role("heading", name="내 관심 상품")).to_be_visible()
        p.goto(BASE + "/admin/users")
        expect(p.get_by_role("heading", name="관리자 전용 화면입니다")).to_be_visible()
        p.goto(BASE + "/login")
        p.get_by_role("button", name="관리자 테스트").click()
        expect(p.get_by_role("link", name="관리자 센터")).to_be_visible()
        p.goto(BASE + "/admin/users")
        expect(p.get_by_role("heading", name="관리자 · 회원 관리")).to_be_visible()
        expect(p.get_by_role("table")).to_be_visible()

    def test_alerts_and_ai(self):
        p = self.page
        p.goto(BASE + "/alerts")
        p.get_by_role("button", name="모두 읽음").click()
        expect(p.get_by_role("button", name="모두 읽음")).to_be_disabled()
        p.get_by_label("읽지 않은 알림만").check()
        expect(p.get_by_role("heading", name="새로운 가격 소식을 기다리는 중이에요")).to_be_visible()
        p.goto(BASE + "/product/1")
        p.get_by_role("button", name="AI 구매 조언", exact=True).click()
        p.get_by_role("button", name="구매 조언 받기").click()
        expect(p.get_by_text("규칙 기반 분석", exact=True)).to_be_visible()
        p.get_by_role("link", name="AI와 상담하기").click()
        p.get_by_role("button", name="어느 쇼핑몰이 제일 싸?").click()
        expect(p.get_by_role("log")).to_contain_text("실구매가가")

    def test_filters_and_empty_results(self):
        p = self.page
        p.goto(BASE + "/search")
        p.get_by_role("button", name="디지털", exact=True).click()
        expect(p.get_by_role("heading", name="세탁세제 3L")).to_have_count(0)
        p.get_by_label("상품 정렬").select_option("price")
        p.get_by_label("지금 구매 추천만").check()
        expect(p.get_by_role("heading", name="무선 이어폰 X2", exact=True)).to_be_visible()
        p.get_by_role("search", name="결과 내 상품 검색").get_by_role("searchbox").fill("없는상품-908172")
        p.get_by_role("search", name="결과 내 상품 검색").get_by_role("button", name="가격 검색").click()
        expect(p.get_by_role("heading", name="조건에 맞는 상품이 없어요")).to_be_visible()
        p.get_by_role("button", name="검색 조건 초기화").click()
        expect(p.get_by_role("heading", name="무선 이어폰 X2", exact=True)).to_be_visible()

    def test_all_customer_routes_at_three_widths(self):
        p = self.page
        for width in (375, 768, 1440):
            p.set_viewport_size({"width": width, "height": 950})
            for route in ("/", "/search", "/product/1", "/watchlist", "/alerts", "/login", "/signup", "/chat/1", "/privacy", "/missing"):
                with self.subTest(width=width, route=route):
                    p.goto(BASE + route)
                    expect(p.locator("main h1, main h3").first).to_be_visible()
                    expect(p.get_by_role("heading", name="화면을 불러오지 못했습니다")).to_have_count(0)
                    self.assertTrue(p.evaluate("document.documentElement.scrollWidth <= innerWidth"), route)

    def test_same_origin_guest_and_error_retry(self):
        # 운영과 같은 상대 API 주소를 사용하되 모든 요청은 로컬 가짜 응답으로 제한한다.
        p = self.page
        p.route("**/js/config.js", lambda r: r.fulfill(
            content_type="application/javascript", body='window.APP_CONFIG={API_BASE_URL:"/"};',
        ))
        p.evaluate("localStorage.clear()")
        attempts = []
        def backend(route):
            if route.request.url.endswith("/deals/today"):
                attempts.append(1)
                route.fulfill(status=503 if len(attempts) == 1 else 200,
                              content_type="application/json",
                              body='{"code":"UNAVAILABLE","message":"가격 수집 서버 점검 중입니다."}' if len(attempts) == 1 else '{"timing":[],"drops":[]}')
            else:
                route.fulfill(status=401, content_type="application/json",
                              body='{"code":"UNAUTHORIZED","message":"로그인이 필요합니다."}')
        p.route("**/api/v1/**", backend)
        p.goto(BASE)
        expect(p.get_by_role("alert")).to_contain_text("가격 수집 서버 점검 중입니다.")
        p.get_by_role("button", name="다시 시도", exact=True).click()
        expect(p.get_by_role("heading", name="이 조건의 추천 상품이 아직 없어요")).to_be_visible()
        p.goto(BASE + "/watchlist")
        expect(p).to_have_url(re.compile(r"/login\?next="))


if __name__ == "__main__":
    unittest.main()
