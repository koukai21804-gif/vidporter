# 贡献指南

感谢参与！vidporter 的核心设计是「平台适配器插件化」，大部分贡献都属于
添加或修复某个平台，非常欢迎。

## 开发环境

```bash
git clone https://github.com/koukai21804-gif/vidporter.git
cd vidporter
pip install -e ".[dev]"
```

日常检查（提交前请确保全部通过）：

```bash
pytest                    # 离线单测，不需要联网
ruff check src tests
ruff format --check src tests
```

## 添加新平台

1. 新建 `src/vidporter/platforms/<name>.py`，继承 `BaseExtractor`：

   ```python
   class MyPlatformExtractor(BaseExtractor):
       name = "myplatform"
       display_name = "我的平台"
       domains = ("myplatform.com",)          # 会自动匹配子域名

       def extract(self, url: str, ctx: ExtractContext) -> MediaInfo:
           client = ctx.get_client()
           canonical = resolve_url(client, url)          # 需要时跟随重定向
           data = extract_json_after_marker(html, "window.__STATE__")
           ...
           return MediaInfo(platform=self.name, ..., formats=[StreamFormat(...)])
   ```

2. 在 `src/vidporter/registry.py` 注册。
3. **离线测试是必须的**：把脱敏的页面样本放进 `tests/fixtures/`，
   用 `httpx.MockTransport` 模拟响应（参考 `tests/conftest.py` 与
   `tests/test_douyin.py`）。不要提交任何 cookie、token 或个人数据。
4. 更新 README 的「支持矩阵」。

工具约定：

- 解析失败抛 `ExtractionError` / `UnsupportedURLError`，引擎会自动回退到
  yt-dlp 兜底，不要在适配器里自行 try/except 吞掉
- 页面 JSON 提取用 `utils.net.extract_json_after_marker`（raw_decode，
  比正则到 `</script>` 稳）
- 下载直链可能需要防盗链头，放进 `MediaInfo.download_headers`

## 需要登录的平台

`ctx.cookies_for(platform)` 会返回该平台 cookie 文件路径（存在时），
配合 `vidporter.cookies.netscape` 读取；请求头里用 `Referer` + cookies。

## 提交规范

- 一个 PR 聚焦一件事
- commit message 用祈使句，例如 `add kuaishou gallery support`
- 新功能请补测试；修 bug 请附上能复现的回归测试

## 行为准则

保持友善、尊重。举报不当行为请开 issue 联系维护者。
