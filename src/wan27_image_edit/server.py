"""万相2.7 图像编辑（多图参考）MCP 服务。

通过阿里云百炼（华北2·北京）异步接口封装一个 MCP 工具：
传入 1-9 张参考图（公网 URL 或 data:image;base64 字符串）+ 文字指令，
返回生成图像的 URL（有效期 24 小时）。

密钥与业务空间 ID 从环境变量读取：
  - DASHSCOPE_API_KEY : 百炼 API Key（必填）
  - WAN_WORKSPACE_ID  : 业务空间 ID，默认内置（北京专属域名 {id}.cn-beijing.maas.aliyuncs.com）
"""

import os
import time

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wan27-image-edit")

# ---- 可被环境变量覆盖的配置 ----
DEFAULT_WORKSPACE_ID = "ws-bw8c2tma2afa2fsl"
REGION_HOST = "cn-beijing"
VALID_MODELS = ("wan2.7-image-pro", "wan2.7-image")
VALID_SIZES = ("1K", "2K", "4K")

# 轮询设置
POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 300


def _base_url() -> str:
    ws = os.getenv("WAN_WORKSPACE_ID", DEFAULT_WORKSPACE_ID).strip()
    bad = [(i, c) for i, c in enumerate(ws) if ord(c) > 255]
    if bad:
        where = "、".join(f"位置{i}的「{c}」" for i, c in bad[:5])
        raise RuntimeError(
            f"WAN_WORKSPACE_ID 含有非 ASCII 字符（{where} 等），请检查配置。"
        )
    return f"https://{ws}.{REGION_HOST}.maas.aliyuncs.com/api/v1"


def _api_key() -> str:
    key = os.getenv("DASHSCOPE_API_KEY", "")
    if not key:
        raise RuntimeError("环境变量 DASHSCOPE_API_KEY 未设置")
    # 复制粘贴常带入首尾换行/空格，先去除
    key = key.strip()
    # HTTP 请求头只允许 latin-1 字符。Key 一旦混入全角字符、中文、智能引号、
    # 零宽空格等非 ASCII 字符，urllib3 会抛 'latin-1' codec can't encode 这类
    # 晦涩异常。这里提前给出可读报错，直接指出是哪个字符、在什么位置。
    bad = [(i, c) for i, c in enumerate(key) if ord(c) > 255]
    if bad:
        where = "、".join(f"位置{i}的「{c}」" for i, c in bad[:5])
        more = " 等" if len(bad) > 5 else ""
        raise RuntimeError(
            f"DASHSCOPE_API_KEY 含有非 ASCII 字符（{where}{more}），"
            f"HTTP 请求头无法编码。请重新从百炼控制台复制 Key，"
            f"注意不要用全角字符、智能引号或结尾空格。"
        )
    return key


def _auth_header() -> dict:
    return {"Authorization": f"Bearer {_api_key()}"}


@mcp.tool()
def wan27_image_edit(
    prompt: str,
    images: list,
    model: str = "wan2.7-image-pro",
    size: str = "2K",
    n: int = 1,
    watermark: bool = False,
    seed: int = None,
) -> str:
    """万相2.7 图像编辑（多图参考）。

    参数:
      prompt: 文字指令，描述如何编辑/融合（≤5000 字符）。例如“把图2的涂鸦喷绘在图1的汽车上”。
      images: 1-9 张参考图，按数组顺序定义“图1/图2...”。每项为公网可访问 URL 或
              data:image/{jpeg|png|webp};base64,<...> 字符串。图像格式 JPEG/JPG/PNG(无透明)/BMP/WEBP，
              宽高 [240,8000]px、宽高比 [1:8,8:1]、单张 ≤20MB。
      model: wan2.7-image-pro（专业版）或 wan2.7-image（更快）。
      size: 输出分辨率规格，1K / 2K / 4K。图像编辑场景 pro 与 image 最高均 2K；4K 仅文生图可用。
      n: 生成张数，1-4。
      watermark: 是否在右下角加“AI生成”水印，默认 False。
      seed: 随机种子 [0,2147483647]，相同 seed 结果相对稳定（可选）。

    返回: 生成图像的 URL 列表（PNG，链接 24 小时内有效，请及时下载保存）。
    """
    if model not in VALID_MODELS:
        raise ValueError(f"model 只能是 {' 或 '.join(VALID_MODELS)}")
    if not isinstance(images, list) or not (1 <= len(images) <= 9):
        raise ValueError("images 必须是 1-9 张图片的数组")
    if size not in VALID_SIZES:
        raise ValueError(f"size 只能是 {' / '.join(VALID_SIZES)}")
    if not (1 <= int(n) <= 4):
        raise ValueError("n 取值范围 1-4")
    if not prompt or not prompt.strip():
        raise ValueError("prompt 不能为空")

    # 图像在前、文字在后，符合“图1/图2”按数组顺序引用的语义
    content = [{"image": img} for img in images]
    content.append({"text": prompt})

    parameters = {"size": size, "n": int(n), "watermark": bool(watermark)}
    if seed is not None:
        parameters["seed"] = int(seed)

    body = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": parameters,
    }

    base = _base_url()
    create_url = f"{base}/services/aigc/image-generation/generation"
    headers = {**_auth_header(), "Content-Type": "application/json", "X-DashScope-Async": "enable"}

    resp = requests.post(create_url, headers=headers, json=body, timeout=60)
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"创建任务返回非 JSON: HTTP {resp.status_code} {resp.text[:200]}")

    if resp.status_code != 200 or "output" not in data or "task_id" not in data.get("output", {}):
        raise RuntimeError(
            f"创建任务失败: HTTP {resp.status_code} code={data.get('code')} message={data.get('message')}"
        )

    task_id = data["output"]["task_id"]
    query_url = f"{base}/tasks/{task_id}"

    deadline = time.time() + POLL_TIMEOUT_SEC
    while time.time() < deadline:
        st = requests.get(query_url, headers=_auth_header(), timeout=30).json()
        status = st.get("output", {}).get("task_status")
        if status == "SUCCEEDED":
            urls = []
            for choice in st["output"].get("choices", []):
                for c in choice.get("message", {}).get("content", []):
                    if c.get("type") == "image":
                        urls.append(c["image"])
            usage = st.get("usage", {})
            if not urls:
                raise RuntimeError(f"任务成功但未解析到图像 URL: {st}")
            lines = [f"生成成功，共 {len(urls)} 张（URL 24 小时内有效，请及时下载）："]
            lines += [f"  [{i+1}] {u}" for i, u in enumerate(urls)]
            lines.append(f"尺寸: {usage.get('size')} | 张数: {usage.get('image_count')} | task_id: {task_id}")
            return "\n".join(lines)
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(
                f"任务未成功: status={status} code={st.get('code')} message={st.get('message')}"
            )
        time.sleep(POLL_INTERVAL_SEC)

    raise RuntimeError(f"任务超时（{POLL_TIMEOUT_SEC}s）仍未完成，task_id={task_id}")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
