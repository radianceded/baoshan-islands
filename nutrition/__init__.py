"""
儿童营养餐智能分配系统 — 模块初始化
"""

from . import models
from . import engine
from . import routes
from . import security
from . import import_export

__version__ = "1.0.0"
__all__ = ["models", "engine", "routes", "security", "import_export", "init_app"]


def init_app(app):
    """注册到现有 Flask 应用"""
    return routes.init_app(app)
