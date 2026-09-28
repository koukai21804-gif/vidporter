"""统一异常体系。CLI 捕获这些异常并给出可读的错误信息。"""


class VidporterError(Exception):
    """所有 vidporter 异常的基类。"""


class UnsupportedURLError(VidporterError):
    """URL 不属于任何已知平台，或无法从中解析出目标内容。"""


class ExtractionError(VidporterError):
    """平台解析失败：页面结构变化、需要登录、被风控等。"""


class CaptureRequiredError(VidporterError):
    """该内容只能通过本地抓包（嗅探）获得，无法直接解析。

    典型场景：微信视频号。视频流经过加密域名分发，
    需要客户端播放时由本地代理捕获真实地址。
    """

    def __init__(self, message: str, guidance: str = "") -> None:
        super().__init__(message)
        self.guidance = guidance


class DownloadError(VidporterError):
    """下载过程失败（网络、HTTP 状态码、写盘等）。"""


class MissingDependencyError(VidporterError):
    """缺少可选依赖。"""


class FFmpegNotFoundError(VidporterError):
    """需要 ffmpeg 但未安装或不在 PATH 中。"""
