"""自定义业务异常。"""


class BizException(Exception):
    """业务异常，由全局异常处理器转换为统一响应。"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthException(BizException):
    """认证/授权异常，默认 401。"""

    def __init__(self, message: str = "未认证或凭证无效", status_code: int = 401):
        super().__init__(code="AUTH_ERROR", message=message, status_code=status_code)
