"""Lỗi hiển thị cho người dùng, viết bằng tiếng Việt dễ hiểu."""
import requests


class UserError(Exception):
    """Lỗi có nội dung đã sẵn sàng để hiện thẳng lên web."""


def friendly(exc: Exception) -> str:
    """Đổi một lỗi bất kỳ thành câu thông báo cho người dùng."""
    if isinstance(exc, UserError):
        return str(exc)

    name = type(exc).__name__
    if name == "NoAudioReceived":
        return ("Dịch vụ giọng đọc (edge-tts) tạm thời không trả về âm thanh. "
                "Hãy chờ khoảng 1 phút rồi bấm \"Thử lại\". "
                "Các cảnh đã làm xong sẽ không phải làm lại.")

    code = getattr(exc, "code", None)
    if code == 429:
        return ("Gemini đã hết hạn mức miễn phí trong lúc này. "
                "Hãy chờ vài phút rồi bấm \"Thử lại\".")
    if isinstance(code, int) and code >= 500:
        return "Gemini đang quá tải. Hãy chờ vài phút rồi bấm \"Thử lại\"."

    if isinstance(exc, requests.RequestException):
        return f"Lỗi mạng khi gọi dịch vụ bên ngoài: {str(exc)[:300]}"

    return (str(exc) or name)[:600]
