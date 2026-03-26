#!/usr/bin/env python3
"""Generate Pamir AI market research PDF report."""

from fpdf import FPDF
import json

FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

class Report(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("zh", "", FONT_PATH)
        self.add_font("zh", "B", FONT_PATH)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font("zh", "", 8)
            self.set_text_color(128)
            self.cell(0, 8, "Pamir AI 市场调研报告", align="R")
            self.ln(4)
            self.set_draw_color(200)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("zh", "", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"第 {self.page_no()} 页", align="C")

    def section_title(self, title):
        self.set_font("zh", "B", 14)
        self.set_text_color(20, 60, 120)
        self.ln(4)
        self.cell(0, 10, title)
        self.ln(8)
        self.set_draw_color(20, 60, 120)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def sub_title(self, title):
        self.set_font("zh", "B", 11)
        self.set_text_color(40, 80, 140)
        self.ln(2)
        self.cell(0, 8, title)
        self.ln(7)

    def body_text(self, text):
        self.set_font("zh", "", 10)
        self.set_text_color(30)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def bullet(self, text):
        self.set_font("zh", "", 10)
        self.set_text_color(30)
        x = self.get_x()
        self.cell(6, 6, "-")
        self.multi_cell(0, 6, text)
        self.ln(1)

    def kv(self, key, value):
        self.set_font("zh", "B", 10)
        self.set_text_color(60)
        self.cell(45, 6, key + ":")
        self.set_font("zh", "", 10)
        self.set_text_color(30)
        self.multi_cell(0, 6, str(value))
        self.ln(1)

    def table_row(self, cells, widths, bold=False):
        self.set_font("zh", "B" if bold else "", 9)
        h = 7
        for i, c in enumerate(cells):
            self.cell(widths[i], h, str(c), border=1, align="C" if bold else "L")
        self.ln(h)


pdf = Report()

# --- Cover page ---
pdf.add_page()
pdf.ln(60)
pdf.set_font("zh", "B", 28)
pdf.set_text_color(20, 60, 120)
pdf.cell(0, 15, "Pamir AI", align="C")
pdf.ln(14)
pdf.set_font("zh", "B", 20)
pdf.set_text_color(60)
pdf.cell(0, 12, "市场调研报告", align="C")
pdf.ln(20)
pdf.set_font("zh", "", 12)
pdf.set_text_color(100)
pdf.cell(0, 8, "2026年3月", align="C")
pdf.ln(8)
pdf.cell(0, 8, "Edge AI Agent Hardware", align="C")

# --- 1. Company Overview ---
pdf.add_page()
pdf.section_title("1. 公司概况")
pdf.kv("公司名称", "PamirAI Inc.")
pdf.kv("成立时间", "2024年")
pdf.kv("总部", "San Francisco, CA, USA")
pdf.kv("创始人", "Kevin (Chengming) Zhang, Tianqi Ye")
pdf.kv("定位", "AI agents on affordable hardware, distributing personal intelligence")
pdf.kv("官网", "https://www.pamir.ai/")
pdf.kv("阶段", "Early-stage startup (Open Alpha)")
pdf.ln(4)
pdf.body_text(
    "Pamir AI 是一家 2024 年成立于旧金山的 AI 硬件初创公司，致力于将 AI Agent 运行在"
    "低成本的专用硬件上，让每个人都能拥有属于自己的 AI「大脑」。公司核心理念类似于 "
    "Raspberry Pi 对计算的普及——让 AI 开发不再依赖昂贵的订阅和高性能云服务器。"
)

# --- 2. Funding ---
pdf.section_title("2. 融资情况")
pdf.kv("融资阶段", "Pre-seed / Early-stage")
pdf.kv("估值", "未公开")
pdf.ln(2)
pdf.sub_title("已知投资方")
for inv in ["Founders, Inc.", "Samsung NEXT Ventures", "iSeed Ventures", "Llama Ventures", "Neo"]:
    pdf.bullet(inv)
pdf.ln(2)
pdf.body_text(
    "Pamir AI 尚未有公开的正式定价融资轮次，但已获得多家知名机构支持。"
    "其中 Samsung NEXT 的参与尤为值得关注，意味着该公司在硬件供应链方面可能获得战略资源。"
)

# --- 3. Products ---
pdf.section_title("3. 产品线")

pdf.sub_title("3.1 Distiller Alpha Dev Kit ($250)")
pdf.body_text(
    "口袋大小的 Linux 计算机，专为 AI Agent 24/7 无人值守运行设计。"
    "预装 ClawdBot (Claude Code agent)，扫码即可在浏览器中打开 VS Code 远程开发。"
    "Alpha 批次已售罄，日产 10-15 台，交付周期 2-3 周。"
)

pdf.sub_title("硬件规格")
specs = [
    ("处理器", "64-bit ARM @ 2.4GHz"),
    ("内存", "8GB RAM"),
    ("存储", "32GB eMMC"),
    ("连接", "Wi-Fi, Bluetooth, USB-C"),
    ("I/O 协议", "I2C/SPI, UART, GPIO, PWM"),
    ("显示", "E-ink 显示屏"),
    ("音频", "内置麦克风 + 扬声器"),
    ("本地 AI", "3B 参数模型"),
]
for k, v in specs:
    pdf.kv(k, v)

pdf.ln(2)
pdf.sub_title("本地推理性能")
widths = [60, 60, 60]
pdf.table_row(["模型", "参数量", "速度"], widths, bold=True)
pdf.table_row(["Qwen3", "0.6B", "~21 tokens/s"], widths)
pdf.table_row(["Qwen3", "1.7B", "~9 tokens/s"], widths)

pdf.ln(4)
pdf.sub_title("3.2 Agent Computer — 下一代 (2026 夏季)")
pdf.body_text(
    "从零开始设计的专用 Agent 计算机。搭载 8 核 ARM 处理器、内置电池、全新外形设计。"
    "Alpha 批次已售罄，目前开放预约注册。将是 Pamir 的关键里程碑产品。"
)

# --- 4. Target Market ---
pdf.section_title("4. 目标市场")
pdf.sub_title("核心用户群")
users = [
    "开发者 — 需要 24/7 AI 编码助手、自动测试和部署",
    "硬件工程师 — 嵌入式系统开发 (刷机、测试、迭代)",
    "创客/Maker — 非专业人士想用硬件构建项目",
    "隐私敏感用户 — 希望本地运行 AI，数据不离开设备",
]
for u in users:
    pdf.bullet(u)

pdf.ln(2)
pdf.sub_title("核心使用场景")
cases = [
    "Agentic Workflows: AI Agent 自主编码、测试、部署，持续数小时/天",
    "嵌入式开发: 通过 USB-C 多协议接口直接与传感器和执行器交互",
    "远程开发: 随时随地通过浏览器扫码使用 VS Code",
    "IoT 原型: 智能硬件快速原型开发",
]
for c in cases:
    pdf.bullet(c)

# --- 5. Competitive Landscape ---
pdf.add_page()
pdf.section_title("5. 竞争格局")

pdf.sub_title("产品对比")
w = [42, 28, 28, 46, 46]
pdf.table_row(["产品", "价格", "AI 算力", "优势", "劣势"], w, bold=True)
pdf.table_row(["Pamir Distiller", "$250", "3B 本地", "Agent 专用", "产能有限"], w)
pdf.table_row(["RPi 5+AI HAT+", "$80-150", "13-26T", "生态庞大", "需自行配置"], w)
pdf.table_row(["Jetson Orin Nano", "$249-499", "40-275T", "GPU 高性能", "功耗高价贵"], w)
pdf.table_row(["Google Coral", "$60-150", "4 TOPS", "Google 生态", "性能有限"], w)
pdf.table_row(["BeagleY-AI", "$70-100", "4 TOPS", "集成 AI", "生态不成熟"], w)

pdf.ln(4)
pdf.sub_title("Pamir AI 的差异化优势")
diffs = [
    "市场上唯一专为 AI Agent 24/7 运行设计的硬件产品",
    "预装 ClawdBot (Claude Code)，开箱即用",
    "E-ink 显示屏 + 低功耗 ARM，适合持续运行",
    "USB-C 统一接口支持多种硬件协议 (I2C/SPI/UART/GPIO/PWM)",
    "扫码即可在浏览器中使用 VS Code 远程开发",
    "软硬件一体化方案，大幅降低入门门槛",
]
for d in diffs:
    pdf.bullet(d)

# --- 6. Market Context ---
pdf.section_title("6. 市场背景")
pdf.kv("2025 边缘 AI 市场规模", "$26.14B")
pdf.kv("2030 预测规模", "$58.90B")
pdf.kv("年复合增长率 (CAGR)", "17.6%")
pdf.ln(2)
pdf.sub_title("关键趋势")
trends = [
    "IoT 设备爆发式增长推动边缘 AI 需求",
    "隐私和数据主权意识增强，本地推理受青睐",
    "AI Agent 从云端走向端侧，24/7 自主运行成为新趋势",
    "开发者工具与硬件深度整合 (Claude Code + 专用硬件)",
    "亚太地区增长最快，制造业与半导体产业驱动",
    "Raspberry Pi 6 可能内置 NPU，推动 AI 在单板计算机上的普及",
]
for t in trends:
    pdf.bullet(t)

# --- 7. SWOT ---
pdf.add_page()
pdf.section_title("7. SWOT 分析")

pdf.sub_title("Strengths (优势)")
for s in [
    "独特定位: 市场唯一专为 AI Agent 设计的口袋计算机",
    "价格优势: $250 远低于 Mac Mini ($600)",
    "软硬件一体: 预装 Claude Code，开箱即用",
    "强力投资方: Samsung NEXT 等知名机构背书",
    "开发者友好: 扫码 VS Code、iOS App、开源 SDK",
]:
    pdf.bullet(s)

pdf.sub_title("Weaknesses (劣势)")
for s in [
    "产能有限: 每天仅 10-15 台，难以规模化",
    "本地模型能力受限: 3B 参数模型智能程度有限",
    "早期阶段: Alpha 产品，稳定性和生态待验证",
    "依赖第三方 AI: 核心 Agent 能力依赖 Anthropic Claude API",
    "团队规模小: 早期创业团队，资源有限",
]:
    pdf.bullet(s)

pdf.sub_title("Opportunities (机会)")
for s in [
    "AI Agent 市场爆发: 2026 年 Agent 应用进入主流",
    "边缘 AI 市场快速增长 (CAGR 17.6%)",
    "开发者对专用 AI 硬件需求旺盛 (Alpha 秒售罄)",
    "夏季推出下一代产品，有望大幅提升竞争力",
    "可拓展到教育、IoT、智能家居等垂直领域",
]:
    pdf.bullet(s)

pdf.sub_title("Threats (威胁)")
for s in [
    "Raspberry Pi 6 可能内置 NPU，蚕食低端市场",
    "NVIDIA、Qualcomm 等巨头可能推出类似定位产品",
    "AI 推理能力快速提升，专用硬件可能被通用设备取代",
    "开源社区可在树莓派上复刻类似软件方案",
    "供应链风险: 小批量生产成本高、交付不确定",
]:
    pdf.bullet(s)

# --- 8. Assessment ---
pdf.section_title("8. 综合评估")
pdf.kv("市场契合度", "高 — AI Agent 从概念走向实际应用，开发者需要专用硬件")
pdf.kv("风险等级", "中高 — 早期产品，竞争激烈，需快速迭代和规模化")
pdf.ln(2)
pdf.body_text(
    "Pamir AI 在 AI Agent 专用硬件这一新兴细分市场中占据先发优势。$250 的定价和软硬件一体化"
    "方案形成了独特卖点。Alpha 批次秒售罄说明市场需求真实存在。但产能瓶颈、本地模型能力有限、"
    "以及来自树莓派生态和芯片巨头的潜在竞争是主要挑战。2026 年夏季推出的下一代 Agent Computer "
    "将是关键里程碑。"
)

pdf.sub_title("重点关注事项")
for s in [
    "2026 年夏季 Agent Computer 的发布和市场反应",
    "是否进行正式融资轮 (Seed / Series A)",
    "产能提升和供应链建设进展",
    "与 Anthropic / Claude 的合作深度",
    "开发者社区增长和生态建设",
]:
    pdf.bullet(s)

# --- Output ---
out_path = "/home/user/daily-ai-pulse-data/data/pamir-market-research.pdf"
pdf.output(out_path)
print(f"PDF generated: {out_path}")
