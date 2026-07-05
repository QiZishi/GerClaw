#!/usr/bin/env python3
"""GerClaw 修复验证测试 - 技能管理中间栏 / 折叠首字露出 / 角色文字"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL = "http://localhost:3000"
SHOT_DIR = Path("/tmp/gerclaw_fix_shots")
SHOT_DIR.mkdir(exist_ok=True)

results = []

def log(name, status, detail=""):
    icon = "PASS" if status == "pass" else "FAIL" if status == "fail" else "INFO"
    line = f"[{icon}] {name}" + (f" - {detail}" if detail else "")
    print(line, flush=True)
    results.append({"name": name, "status": status, "detail": detail})

def shot(page, name):
    p = SHOT_DIR / f"{name}.png"
    try: page.screenshot(path=str(p), full_page=True)
    except: pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    print("=" * 60, flush=True)
    print("GerClaw 修复验证测试", flush=True)
    print("=" * 60, flush=True)

    # 加载页面
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("aside", timeout=30000)
        page.wait_for_timeout(2000)
        log("页面加载", "pass")
    except Exception as e:
        log("页面加载", "fail", str(e))
        sys.exit(1)

    # ========== 修复 1: 技能管理按钮位置（新建对话和搜索框之间） ==========
    try:
        # 找到"新建对话"按钮
        new_btn = page.locator("button", has_text="新建对话").first
        # 找到技能管理按钮（在新建对话旁边）
        skill_btn = page.locator('button[aria-label="技能管理"]').first
        expect(new_btn).to_be_visible()
        expect(skill_btn).to_be_visible()
        # 验证它们在同一容器内
        new_box = new_btn.bounding_box()
        skill_box = skill_btn.bounding_box()
        # 技能按钮应该在新建对话按钮右侧（同一行）
        if abs(new_box["y"] - skill_box["y"]) < 10 and skill_box["x"] > new_box["x"]:
            log("技能管理按钮位置（新建对话右侧）", "pass", f"new x={new_box['x']:.0f}, skill x={skill_box['x']:.0f}")
        else:
            log("技能管理按钮位置", "fail", f"位置不对: new={new_box}, skill={skill_box}")
        shot(page, "01_skill_btn_position")
    except Exception as e:
        log("技能管理按钮位置", "fail", str(e))

    # ========== 修复 2: 点击技能管理在中间栏显示 ==========
    try:
        skill_btn = page.locator('button[aria-label="技能管理"]').first
        skill_btn.click()
        page.wait_for_timeout(1500)
        # 中间栏应显示技能管理（main 区域有"技能管理"标题）
        main = page.locator("main").first
        title_in_main = main.locator("text=技能管理").first
        expect(title_in_main).to_be_visible()
        # 验证右侧面板未打开（只有一个 aside 即侧边栏）
        asides = page.locator("aside:visible")
        if asides.count() == 1:
            log("技能管理在中间栏显示", "pass", "右侧面板未打开")
        else:
            log("技能管理在中间栏显示", "info", f"aside count={asides.count()}")
        shot(page, "02_skills_in_main")
    except Exception as e:
        log("技能管理在中间栏显示", "fail", str(e))

    # ========== 修复 2.1: 技能管理有返回按钮 ==========
    try:
        back_btn = page.locator('button[aria-label="返回对话"]').first
        expect(back_btn).to_be_visible()
        log("技能管理返回按钮可见", "pass")
    except Exception as e:
        log("技能管理返回按钮", "fail", str(e))

    # 点击返回按钮
    try:
        back_btn.click()
        page.wait_for_timeout(1000)
        # 应回到聊天视图（欢迎页或消息列表）
        welcome = page.locator("h1").first
        if welcome.count() > 0:
            log("返回对话视图", "pass", f"标题: {welcome.inner_text()[:30]}")
        shot(page, "03_back_to_chat")
    except Exception as e:
        log("返回对话视图", "fail", str(e))

    # ========== 修复 3: 折叠时不显示会话首字 ==========
    try:
        # 折叠侧边栏
        collapse_btn = page.locator('button[aria-label="折叠侧边栏"]').first
        expect(collapse_btn).to_be_visible()
        collapse_btn.click()
        page.wait_for_timeout(500)
        # 折叠后侧边栏宽度应为 64px
        sidebar = page.locator("aside").first
        sb_box = sidebar.bounding_box()
        # 检查侧边栏内是否有会话首字文字（不应有）
        # 折叠后侧边栏内不应有 span 文字（除了图标）
        spans_with_text = sidebar.locator("span:has-text('血'), span:has-text('糖'), span:has-text('头')")
        first_letter_count = spans_with_text.count()
        if first_letter_count == 0:
            log("折叠时不显示会话首字", "pass", f"宽度={sb_box['width']:.0f}px, 首字露出=0")
        else:
            log("折叠时会话首字露出", "fail", f"仍有 {first_letter_count} 个首字露出")
        shot(page, "04_collapsed_clean")
        # 展开
        expand_btn = page.locator('button[aria-label*="展开"]').first
        if expand_btn.count() > 0:
            expand_btn.click()
            page.wait_for_timeout(500)
    except Exception as e:
        log("折叠时不显示会话首字", "fail", str(e))

    # ========== 修复 4: 医生/患者按钮文字随状态变化 ==========
    try:
        # 当前是患者端，应显示"当前：患者"和"点击切换到医生端"
        patient_text = page.locator("text=当前：患者")
        switch_hint = page.locator("text=点击切换到医生端")
        if patient_text.count() > 0 and switch_hint.count() > 0:
            log("患者端文字显示正确", "pass", "'当前：患者' + '点击切换到医生端'")
        else:
            log("患者端文字", "fail", f"patient={patient_text.count()}, hint={switch_hint.count()}")

        # 切换到医生端
        switches = page.locator('[role="switch"]')
        switches.first.click()
        page.wait_for_timeout(1500)
        # 应显示"当前：医生"和"点击切换到患者端"
        doctor_text = page.locator("text=当前：医生")
        switch_hint2 = page.locator("text=点击切换到患者端")
        if doctor_text.count() > 0 and switch_hint2.count() > 0:
            log("医生端文字显示正确", "pass", "'当前：医生' + '点击切换到患者端'")
        else:
            log("医生端文字", "fail", f"doctor={doctor_text.count()}, hint={switch_hint2.count()}")
        shot(page, "05_doctor_role_text")

        # 切回患者端
        switches.first.click()
        page.wait_for_timeout(1000)
    except Exception as e:
        log("医生/患者按钮文字", "fail", str(e))

    # ========== 总结 ==========
    print("=" * 60, flush=True)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    print(f"总计: {len(results)} 项 | PASS: {passed} | FAIL: {failed}", flush=True)
    print(f"截图: {SHOT_DIR}", flush=True)
    print("=" * 60, flush=True)

    browser.close()
    sys.exit(0 if failed == 0 else 1)
