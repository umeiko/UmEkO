"""Visual tool wording and capability guidance shared by main and file agents."""

IMAGE_REASONING_DESCRIPTION = (
    "通用图像理解与推理工具：使用视觉模型分析一张或多张图片，"
    "支持内容描述、图表解读、界面与布局分析、图片比较、按标准检查和文字识别（OCR）。"
    "prompt 写明用户的问题、必要上下文和输出要求；"
    "专业质检按当前 Skill 提供的检查标准、判定规则和报告流程执行，不自行编造标准。"
    "执行时流式返回结果。"
)

IMAGE_REASONING_PROMPT_DESCRIPTION = (
    "发给视觉模型的完整任务、上下文和输出要求，例如解读图表、解释界面、比较图片或识别文字；"
    "专业质检须附上 Skill 中相关检查标准和判定规则。"
)


def image_input_guidance(*, native_vision: bool, reasoning_available: bool,
                         delegated_reasoning: bool = False, model_label: str = "主模型") -> str:
    guidance = "\n\n[图像能力与调用方式]\n"
    if native_vision:
        guidance += f"当前{model_label}原生图像输入：已开启，可以处理本轮用户图片；读取其他本地图片可用 read_image。\n"
    if reasoning_available:
        guidance += (
            "如果用户附带了图片内容，在你可以知道该图片路径的情况下，"
            "使用 image_reasoning 工具完成图像理解，并且如实描述工具的输出结果，或错误信息。\n"
        )
    elif delegated_reasoning:
        guidance += (
            "如果用户附带了图片内容且已知图片路径，使用 delegate_task 委派给文件子 Agent，"
            "让它使用 image_reasoning 完成图像理解；提供用户问题、图片路径和必要上下文，"
            "并如实描述工具的输出结果，或错误信息。\n"
        )
    elif not native_vision:
        guidance += (
            "当前会话没有可用的视觉分析能力。任务需要理解图片时明确说明需要在 Provider / Model "
            "配置视觉模型或启用支持图片的模型；不要虚构图片内容或调用不存在的工具。\n"
        )
    if native_vision or reasoning_available or delegated_reasoning:
        guidance += (
            "专业图像质检与报告任务仍须遵循相关 Skill：确保已获得完整工作指引，"
            "按其角色分工、检查标准、证据要求、PASS/WARN/FAIL/NA 判定和报告流程执行。"
            "若当前 Skill 要求主 Agent 只编排并委派检查，必须遵守，不用通用看图流程替代它。"
            "工具失败时报告实际错误；无法检查的内容不能记为通过。"
        )
    return guidance
