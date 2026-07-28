"""Contract tests for the Vue 3 SPA build artifacts of ``x web``.

The frontend is a Vite-built Vue app whose source lives in ``web/`` and whose
artifacts are emitted into ``core/web/static/``. These tests assert the
*served artifact* contract — structure, no-CDN, security invariants — rather
than implementation details of any single component.

They run against whatever is currently built in ``core/web/static/``. If the
artifacts are stale, run ``cd web && npm run build`` first.
"""

from __future__ import annotations

import re
from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "core" / "web" / "static"


def _read(relative_path: str) -> str:
    return (STATIC_DIR / relative_path).read_text(encoding="utf-8")


def _all_js() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                     for p in (STATIC_DIR / "assets").glob("*.js"))


def _all_css() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                     for p in (STATIC_DIR / "assets").glob("*.css"))


# ---- 结构与入口 ----------------------------------------------------------


def test_build_emits_spa_entry_and_hashed_assets() -> None:
    index = STATIC_DIR / "index.html"
    assert index.is_file(), "index.html missing — run `cd web && npm run build`"

    html = index.read_text(encoding="utf-8")
    assert 'id="app"' in html, "SPA mount point missing"
    assert 'type="module"' in html, "module entry script missing"

    assets = STATIC_DIR / "assets"
    assert assets.is_dir(), "assets/ directory missing"
    js = list(assets.glob("*.js"))
    css = list(assets.glob("*.css"))
    assert js, "no JS bundles emitted"
    assert css, "no CSS bundles emitted"
    assert len(js) > 1, "route-level code splitting is missing"


def test_entry_uses_relative_paths_for_any_mount() -> None:
    html = _read("index.html")
    assert re.search(r'src="\./assets/', html), "entry script must use relative ./assets path"
    assert re.search(r'href="\./assets/', html), "stylesheet must use relative ./assets path"


# ---- 无外链（本地工具，零 CDN） ------------------------------------------


def test_no_remote_resources_anywhere() -> None:
    text = _read("index.html")
    assert 'src="http' not in text
    assert 'href="http' not in text
    for blob in (_all_js(), _all_css()):
        assert "https://fonts." not in blob
        assert "url(http" not in blob
        assert "@import url(http" not in blob


# ---- 安全契约 ------------------------------------------------------------


def test_secret_list_bundle_does_not_fetch_plaintext() -> None:
    """密钥列表 bundle 绝不应调用会返回明文 value 的 getSecret。

    删除走 DELETE 单密钥端点是允许的（不返回明文）；真正危险的是 GET 明文
    端点 getSecret，它只应出现在 SecretView / SecretEdit 的 bundle 里。
    """
    list_bundle = next(STATIC_DIR.glob("assets/SecretListView-*.js"), None)
    assert list_bundle, "SecretListView bundle missing"
    src = list_bundle.read_text(encoding="utf-8", errors="ignore")
    assert "getSecret" not in src


def test_plaintext_view_requires_confirmation_before_fetch() -> None:
    """查看明文的 bundle 必须先弹确认再请求数据。"""
    view_bundle = next(STATIC_DIR.glob("assets/SecretView-*.js"), None)
    assert view_bundle, "SecretView bundle missing"
    src = view_bundle.read_text(encoding="utf-8", errors="ignore")
    assert "我已了解" in src, "plaintext reveal confirmation text missing"


def test_secret_editor_supports_text_and_secret_fields() -> None:
    editor = next(STATIC_DIR.glob("assets/SecretEditView-*.js"), None)
    assert editor, "SecretEditView bundle missing"
    src = editor.read_text(encoding="utf-8", errors="ignore")
    for text in ("添加字段", "普通文本", "密钥信息", "设为主密钥"):
        assert text in src, f"multi-field editor control missing: {text}"


def test_secret_edit_requires_confirmation_before_fetching_values() -> None:
    editor = next(STATIC_DIR.glob("assets/SecretEditView-*.js"), None)
    assert editor, "SecretEditView bundle missing"
    src = editor.read_text(encoding="utf-8", errors="ignore")
    assert "编辑将读取全部字段值" in src
    assert "我已了解，继续编辑" in src


def test_secret_detail_keeps_per_field_reveal_copy_and_safe_links() -> None:
    view = next(STATIC_DIR.glob("assets/SecretView-*.js"), None)
    assert view, "SecretView bundle missing"
    src = view.read_text(encoding="utf-8", errors="ignore")
    for text in ("普通文本", "密钥信息", "主密钥", "复制字段"):
        assert text in src, f"per-field detail behavior missing: {text}"
    assert "noopener noreferrer" in src, "external URL must isolate opener"


def test_token_persistence_uses_localstorage_key() -> None:
    assert "x_web_token" in _all_js(), "localStorage token key missing"


def test_frontend_discovers_optional_auth_mode() -> None:
    """The built SPA must read the backend's ``auth_required`` capability."""
    assert "auth_required" in _all_js(), "optional auth discovery missing"


def test_secret_confirmation_can_be_disabled_and_persisted() -> None:
    """Built UI exposes the opt-out and stores it through the narrow API."""
    js = _all_js()
    assert "不再提示" in js
    assert "secret_confirmation_required" in js
    assert "/api/preferences" in js
    assert "web_secret_confirmation" in js


def test_topbar_offers_hierarchical_parent_navigation() -> None:
    """Child pages expose one accessible, responsive parent-navigation control."""
    js = _all_js()
    css = _all_css()
    assert "返回上一级" in js
    assert "back-btn" in js
    assert ".back-btn" in css
    assert "parent" in js


# ---- 可访问性 ------------------------------------------------------------


def test_login_bundle_keeps_accessibility_hooks() -> None:
    login = next(STATIC_DIR.glob("assets/LoginView-*.js"), None)
    assert login, "LoginView bundle missing"
    src = login.read_text(encoding="utf-8", errors="ignore")
    # Vue 把模板编译成渲染函数：属性以 JS 对象键值存在，非 HTML 字符串。
    assert 'current-password' in src, "autocomplete=current-password missing"
    assert re.search(r"role:[`'\"]alert[`'\"]", src) or 'role="alert"' in src, (
        "role=alert missing"
    )
    assert "token-help login-error" in src, "aria-describedby targets missing"


def test_css_keeps_accessibility_and_responsive_rules() -> None:
    css = _all_css()
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "@media" in css, "responsive breakpoints missing"
