# wan27-image-edit

万相2.7 **图像编辑（多图参考）** 的 MCP 服务，封装阿里云百炼（华北2·北京）异步生图接口。
通过 `uvx` 从 GitHub 直接安装运行，可一键部署到阿里云函数计算（FC）「创建 MCP 服务」页面。

## 暴露的工具

`wan27_image_edit` — 传入 1–9 张参考图 + 文字指令，返回生成图像 URL（PNG，24 小时内有效）。

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `prompt` | 文字编辑指令（≤5000 字符），如“把图2的涂鸦喷绘在图1的汽车上” | 必填 |
| `images` | 1–9 张图，数组顺序=图1/图2…；公网 URL 或 `data:image/...;base64,<...>` | 必填 |
| `model` | `wan2.7-image-pro` / `wan2.7-image` | `wan2.7-image-pro` |
| `size` | `1K` / `2K` / `4K`（图像编辑场景最高 2K） | `2K` |
| `n` | 生成张数 1–4 | `1` |
| `watermark` | 右下角是否加“AI生成”水印 | `false` |
| `seed` | 随机种子 0–2147483647 | 可选 |

## 环境变量

- `DASHSCOPE_API_KEY`（必填）：百炼 API Key。
- `WAN_WORKSPACE_ID`（可选）：业务空间 ID，默认内置 `ws-bw8c2tma2afa2fsl`，请求域名 `https://{id}.cn-beijing.maas.aliyuncs.com`。

## 本地快速自测（可选）

```bash
# 需要 uv（pip install uv）
export DASHSCOPE_API_KEY=sk-xxxx
uvx --from /绝对路径/到/本仓库 wan27-image-edit
# 或用 MCP Inspector 连 STDIO 测试：
npx @modelcontextprotocol/inspector uvx --from . wan27-image-edit
```

---

## 部署步骤

### 1. 推到 GitHub（公开仓库）

在 GitHub 新建一个**公开**仓库 `wan27-image-edit`，然后：

```bash
cd wan27-image-edit
git init
git add .
git commit -m "init wan2.7 image-edit MCP server"
git branch -M main
git remote add origin https://github.com/nanchenyi/wan27-image-edit.git
git push -u origin main
```

> 代码里不含任何密钥，公开只是暴露这层薄封装源码。

### 2. 阿里云 FC「创建 MCP 服务」页面填写

- **服务名称**：`wan27-image-edit`
- **安装方式**：选 `uvx`
- **部署方式**：打开 **极速模式**（SSE 会话更稳；按 0.13 元/时计费）
- **部署地域**：华北2（北京）
- **MCP 服务配置**：粘贴下面 JSON，只把 `DASHSCOPE_API_KEY` 换成你自己的真实 Key

```json
{
  "mcpServers": {
    "wan27-image-edit": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/nanchenyi/wan27-image-edit.git",
        "wan27-image-edit"
      ],
      "env": {
        "DASHSCOPE_API_KEY": "sk-你的真实Key",
        "WAN_WORKSPACE_ID": "ws-bw8c2tma2afa2fsl"
      }
    }
  }
}
```

> 若页面提供「变量管理 / 服务变量（加密）」，更推荐把 `DASHSCOPE_API_KEY` 作为加密变量托管，配置里用变量引用，避免明文出现在 JSON。

### 3. 保存后测试

页面「测试」入口选择 SSE / 对应传输类型，调用 `wan27_image_edit`：
传 `prompt` + 至少一张公网可访问的 `images` URL，确认返回图像链接。

## 常见问题

- **鉴权失败 / 跨地域报错**：北京与新加坡的 API Key、域名不通用，确认 Key 与 `cn-beijing` 域名同属北京地域。
- **`current user api does not support synchronous calls`**：本服务走的是异步接口（带 `X-DashScope-Async: enable`），正常不会出现；若自行改造为同步路径需注意。
- **图像 URL 打不开**：链接仅 24 小时有效，请及时下载保存。
- **启动报 `No module named 'mcp.server.fastmcp'`**：依赖已锁定 `mcp>=1.2.0,<2`。mcp 2.x 把 `FastMCP` 改名为 `MCPServer`，不要放开这个上限。
- **`'latin-1' codec can't encode characters`**：这是请求头编码错误，与图像 URL / prompt 内容无关。根因是 `DASHSCOPE_API_KEY`（或 `WAN_WORKSPACE_ID`）里混入了非 ASCII 字符——从网页复制 Key 时常带入全角字符、智能引号、零宽空格或结尾空格。服务现已在调用前校验并直接报出「哪个字符、在什么位置」。请重新从百炼控制台复制 Key，确认输入法处于半角、粘贴后首尾无空格。图像 URL 中的中文路径、`Signature=`、`%3D` 等都在 JSON body 里，不会触发该错误。
