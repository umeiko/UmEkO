"""Visual tool wording and capability guidance shared by main and file agents."""

IMAGE_REASONING_DESCRIPTION = (
    "通用图像理解与推理工具：使用视觉模型分析一张或多张图片，"
    "支持内容描述、图表解读、界面与布局分析、图片比较、按标准检查和文字识别（OCR）。"
    "OCR 只是其中一种用途；用户无需指定 OCR，普通看图问题也可以调用。"
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
    else:
        guidance += f"当前{model_label}原生图像输入：未开启，图片以路径提供，不能把路径或文件名当作图片内容。\n"
    if reasoning_available:
        guidance += (
            "当前工具列表已提供 image_reasoning，具备通用图像理解能力。"
            "原生图像输入未开启时，先用 image_reasoning 分析图片再回答；"
            "不要仅因当前模型不能直接看图就拒答或要求用户更换主模型。\n"
        )
    elif delegated_reasoning:
        guidance += (
            "主 Agent 没有直接图像分析工具，但文件子 Agent 已提供 image_reasoning。"
            "需要看图时用 delegate_task，提供用户问题、图片路径、必要上下文和输出要求；"
            "不要仅因主模型不能直接看图就拒答。\n"
        )
    elif not native_vision:
        guidance += (
            "当前会话没有可用的视觉分析能力。任务需要理解图片时明确说明需要在 Provider / Model "
            "配置视觉模型或启用支持图片的模型；不要虚构图片内容或调用不存在的工具。\n"
        )
    if native_vision or reasoning_available or delegated_reasoning:
        guidance += (
            "image_reasoning 是通用图像理解工具，OCR 只是其一种用途。"
            "普通看图、图表或界面解释按用户意图分析，无需用户说出 OCR，也不要求先有 Skill。"
            "使用给出的实际图片路径，prompt 包含本轮问题及相关上下文，不默认改成文字提取。"
            "只收到图片且目标不明确时，可先简短客观描述，再询问需要关注什么。\n"
            "专业图像质检与报告任务仍须遵循相关 Skill：确保已获得完整工作指引，"
            "按其角色分工、检查标准、证据要求、PASS/WARN/FAIL/NA 判定和报告流程执行。"
            "若当前 Skill 要求主 Agent 只编排并委派检查，必须遵守，不用通用看图流程替代它。"
            "工具失败时报告实际错误；无法检查的内容不能记为通过。"
        )
    return guidance
