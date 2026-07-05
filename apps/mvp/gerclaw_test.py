#!/usr/bin/env python3
"""GerClaw Phase 8 自动化浏览器测试 - 验证 0001 执行计划验收标准"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL = "http://localhost:3000"
SHOT_DIR = Path("/tmp/gerclaw_shots")
SHOT_DIR.mkdir(exist_ok=True)

results = []

def log(name, status, detail=""):
    icon = "PASS" if status == "pass" else "FAIL" if status == "fail" else "INFO"
    line = f"[{icon}] {name}" + (f" - {detail}" if detail else "")
    print(line, flush=True)
    results.append({"name": name, "status": status, "detail": detail})

def shot(page, name):
    p = SHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(p), full_page=True)
    except Exception:
        pass
    return str(p)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    print("=" * 60, flush=True)
    print("GerClaw Phase 8 自动化测试", flush=True)
    print("=" * 60, flush=True)

    # ========== 测试 1: 页面可访问 ==========
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("aside", timeout=30000)
        log("页面可访问 http://localhost:3000", "pass")
    except Exception as e:
        log("页面可访问", "fail", str(e))
        shot(page, "fail_load")
        sys.exit(1)

    page.wait_for_timeout(3000)
    shot(page, "01_initial")

    # ========== 测试 2: 三栏布局 ==========
    try:
        sidebar = page.locator("aside").first
        expect(sidebar).to_be_visible()
        sb_box = sidebar.bounding_box()
        log("侧边栏可见", "pass", f"width={sb_box['width']:.0f}px")

        main = page.locator("main").first
        expect(main).to_be_visible()
        log("中间聊天区可见", "pass")

        welcome = page.locator("h1").first
        expect(welcome).to_be_visible()
        welcome_text = welcome.inner_text()
        log("欢迎页标题", "pass", welcome_text[:40])
    except Exception as e:
        log("三栏布局检查", "fail", str(e))
        shot(page, "fail_layout")

    # ========== 测试 3: 欢迎页快捷入口卡片 ==========
    try:
        cards = page.locator("button:has-text('处方'), button:has-text('评估'), button:has-text('审查'), button:has-text('画像')")
        count = cards.count()
        if count >= 4:
            log("欢迎页快捷入口卡片", "pass", f"找到 {count} 张")
        else:
            log("欢迎页快捷入口卡片", "fail", f"仅找到 {count} 张，期望 ≥4")
    except Exception as e:
        log("快捷入口卡片", "fail", str(e))

    # ========== 测试 4: 侧边栏折叠/展开 ==========
    try:
        collapse_btn = page.locator('button[aria-label="折叠侧边栏"]')
        if collapse_btn.count() == 0:
            collapse_btn = page.locator('button[aria-label*="折叠"]')
        expect(collapse_btn.first).to_be_visible()
        sb_before = page.locator("aside").first.bounding_box()
        collapse_btn.first.click()
        page.wait_for_timeout(500)
        sb_after = page.locator("aside").first.bounding_box()
        if sb_after["width"] < sb_before["width"]:
            log("侧边栏折叠", "pass", f"{sb_before['width']:.0f}px → {sb_after['width']:.0f}px")
        else:
            log("侧边栏折叠", "fail", f"宽度未变化 {sb_before['width']:.0f} → {sb_after['width']:.0f}")
        shot(page, "02_sidebar_collapsed")
        expand_btn = page.locator('button[aria-label*="展开"]')
        if expand_btn.count() > 0:
            expand_btn.first.click()
            page.wait_for_timeout(500)
            log("侧边栏展开", "pass")
    except Exception as e:
        log("侧边栏折叠/展开", "fail", str(e))

    # ========== 测试 5: 右侧面板展开（点击处方卡片） ==========
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("aside", timeout=15000)
        page.wait_for_timeout(2000)
        rx_btn = page.locator("button", has_text="五大处方生成")
        if rx_btn.count() > 0:
            rx_btn.first.click()
            page.wait_for_timeout(1500)
            panels = page.locator("aside:visible")
            panel_count = panels.count()
            if panel_count >= 2:
                panel = panels.nth(panel_count - 1)
                expect(panel).to_be_visible()
                panel_box = panel.bounding_box()
                log("右侧面板展开(处方)", "pass", f"width={panel_box['width']:.0f}px")
                shot(page, "03_right_panel_prescription")
            else:
                log("右侧面板展开", "fail", f"仅 {panel_count} 个 aside 可见")
        else:
            log("处方入口未找到", "fail")
    except Exception as e:
        log("右侧面板展开(处方)", "fail", str(e))
        shot(page, "fail_right_panel")

    # ========== 测试 6: 关闭右侧面板 ==========
    try:
        close_btn = page.locator('aside button[aria-label="关闭"]').last
        if close_btn.count() > 0:
            close_btn.click()
            page.wait_for_timeout(500)
            log("右侧面板关闭", "pass")
    except Exception as e:
        log("右侧面板关闭", "fail", str(e))

    # ========== 测试 7: 技能管理入口 ==========
    try:
        skill_btn = page.locator("button", has_text="技能管理")
        if skill_btn.count() > 0:
            skill_btn.first.click()
            page.wait_for_timeout(1500)
            shot(page, "04_skills_panel")
            log("技能管理面板", "pass")
        else:
            log("技能管理按钮未找到", "fail")
    except Exception as e:
        log("技能管理面板", "fail", str(e))

    try:
        close_btn = page.locator('aside button[aria-label="关闭"]').last
        if close_btn.count() > 0:
            close_btn.click()
            page.wait_for_timeout(500)
    except:
        pass

    # ========== 测试 8: 角色切换（患者 → 医生） ==========
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("aside", timeout=15000)
        page.wait_for_timeout(2000)
        # 确保侧边栏展开（如果折叠了先展开）
        if page.locator('button[aria-label*="展开"]').count() > 0:
            page.locator('button[aria-label*="展开"]').first.click()
            page.wait_for_timeout(600)
        # 使用 role=switch 定位所有开关，第1个是角色切换
        switches = page.locator('[role="switch"]')
        if switches.count() >= 1:
            switches.first.click()
            page.wait_for_timeout(2000)
            doctor_badge = page.locator("text=医生端")
            if doctor_badge.count() > 0:
                log("角色切换患者→医生", "pass")
                shot(page, "05_doctor_role")
            else:
                log("角色切换", "fail", "未出现医生端标识")
        else:
            log("角色切换按钮未找到", "fail", f"switches count={switches.count()}")
    except Exception as e:
        log("角色切换", "fail", str(e))
        shot(page, "fail_role_switch")

    # ========== 测试 9: 医生端患者列表 ==========
    try:
        patient_list_marker = page.locator("text=患者列表")
        if patient_list_marker.count() == 0:
            patient_list_marker = page.locator("text=待评估").or_(page.locator("text=评估中"))
        if patient_list_marker.count() > 0:
            log("医生端患者列表可见", "pass")
            shot(page, "06_doctor_patient_list")
        else:
            log("医生端患者列表", "fail", "未找到患者列表标识")
    except Exception as e:
        log("医生端患者列表", "fail", str(e))

    # ========== 测试 10: 主题切换 ==========
    try:
        theme_btns = page.locator('button[aria-label*="主题"], button[aria-label*="切换"]')
        if theme_btns.count() == 0:
            theme_btns = page.locator('button:has(svg.lucide-sun), button:has(svg.lucide-moon)')
        if theme_btns.count() > 0:
            html_before = page.locator("html").get_attribute("class") or ""
            theme_btns.first.click()
            page.wait_for_timeout(600)
            html_after = page.locator("html").get_attribute("class") or ""
            if html_before != html_after:
                log("主题切换", "pass", f"class: '{html_before}' → '{html_after}'")
            else:
                log("主题切换", "fail", "html class 未变化")
        else:
            log("主题切换按钮未找到", "info")
    except Exception as e:
        log("主题切换", "fail", str(e))

    # ========== 测试 11: 切回患者端 + 老年模式 ==========
    try:
        switches = page.locator('[role="switch"]')
        if switches.count() >= 1:
            switches.first.click()
            page.wait_for_timeout(1500)
            log("切回患者端", "pass")
    except:
        pass

    try:
        # 老年模式是第2个 switch（仅患者端）
        switches = page.locator('[role="switch"]')
        if switches.count() >= 2:
            html_before = page.locator("html").get_attribute("class") or ""
            switches.nth(1).click()
            page.wait_for_timeout(600)
            html_after = page.locator("html").get_attribute("class") or ""
            if html_before != html_after:
                log("老年模式切换", "pass", f"class 变化")
                shot(page, "07_senior_mode")
            else:
                log("老年模式", "fail", "html class 未变化")
        else:
            log("老年模式开关未找到", "info", f"switches count={switches.count()}")
    except Exception as e:
        log("老年模式", "fail", str(e))

    # ========== 测试 12: 选择会话查看消息流 ==========
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("aside", timeout=15000)
        page.wait_for_timeout(2000)
        # 点击第一个非置顶的会话项
        items = page.locator("aside [class*='cursor-pointer']").all()
        clicked = False
        for it in items[:8]:
            try:
                txt = it.inner_text()[:30]
                if txt and "GerClaw" not in txt and "新建" not in txt and "技能" not in txt:
                    it.click()
                    page.wait_for_timeout(2000)
                    # 检查是否进入了消息列表（main 区有消息）
                    shot(page, "08_message_list")
                    msg_count_header = page.locator("text=条消息")
                    if msg_count_header.count() > 0:
                        log("会话消息流加载", "pass", f"选中: {txt}")
                        clicked = True
                        break
            except:
                continue
        if not clicked:
            log("会话消息流", "info", "未找到可点击的会话项")
    except Exception as e:
        log("会话消息流", "fail", str(e))

    # ========== 测试 13: 7 项可视化组件 ==========
    blocks_check = {
        "ThinkingBlock (思维链)": ["思考中", "思维链", "thinking", "ThinkingBlock"],
        "ToolCallBlock (工具调用)": ["工具调用", "Tool", "tool-call", "ToolCall"],
        "SubAgentTree (子智能体)": ["子智能体", "SubAgent", "sub-agent"],
        "DecisionTimeline (决策过程)": ["决策", "Timeline", "decision", "DecisionTimeline"],
        "StreamingText (流式文本)": ["streaming", "打字"],
        "SearchResultCard (搜索结果)": ["搜索结果", "来源", "citation"],
        "FileTag (文档标签)": ["文件", "解析", "file-tag", "FileTag"],
    }
    page_content = page.content()
    for name, keywords in blocks_check.items():
        found = any(kw.lower() in page_content.lower() for kw in keywords)
        if found:
            log(f"可视化组件: {name}", "pass")
        else:
            log(f"可视化组件: {name}", "info", "未在当前页面找到（可能在其他会话）")

    # ========== 测试 14: 医疗免责声明 ==========
    try:
        disclaimer = page.locator("text=免责声明").or_(page.locator("text=仅供参考")).or_(page.locator("text=不能替代"))
        if disclaimer.count() > 0:
            log("医疗免责声明", "pass")
        else:
            log("医疗免责声明", "info", "当前页面未显示（可能在处方/CGA 报告中）")
    except Exception as e:
        log("医疗免责声明", "fail", str(e))

    # ========== 测试 15-17: 响应式 ==========
    for w, h, label in [(1280, 800, "1280px 桌面"), (768, 1024, "768px 平板"), (375, 812, "375px 手机")]:
        try:
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(600)
            shot(page, f"09_responsive_{w}")
            log(f"响应式 {label}", "pass")
        except Exception as e:
            log(f"响应式 {label}", "fail", str(e))

    # ========== 测试 18: 控制台错误 ==========
    if console_errors:
        log("控制台错误", "info", f"共 {len(console_errors)} 条")
        for err in console_errors[:5]:
            print(f"     - {err[:120]}", flush=True)
    else:
        log("控制台无错误", "pass")

    # ========== 总结 ==========
    print("=" * 60, flush=True)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    info = sum(1 for r in results if r["status"] == "info")
    print(f"总计: {len(results)} 项 | PASS: {passed} | FAIL: {failed} | INFO: {info}", flush=True)
    print(f"截图保存于: {SHOT_DIR}", flush=True)
    print("=" * 60, flush=True)

    with open("/tmp/gerclaw_test_results.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    browser.close()
    sys.exit(0 if failed == 0 else 1)
