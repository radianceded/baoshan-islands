"""
安全模块 — 加密/脱敏/权限
cryptography 为可选依赖，未安装时真实姓名明文存储（适合测试环境）
"""

import os
import hashlib
import base64

_ENCRYPTION_SECRET = os.environ.get("NUTRITION_ENCRYPTION_SECRET", "nutrition-demo-key-change-in-production!!")

# cryptography 可选
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


def _get_fernet():
    """生成 Fernet 加密实例（cryptography 不存在时返回 None）"""
    if not _CRYPTO_AVAILABLE:
        return None
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32,
        salt=b"baoshan_nutrition_salt_2026", iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(_ENCRYPTION_SECRET.encode()))
    return Fernet(key)


def encrypt_real_name(name: str) -> str:
    """加密真实姓名。cryptography 不可用时明文存储。"""
    if not name:
        return ""
    f = _get_fernet()
    if f is None:
        return name  # 明文回退
    return f.encrypt(name.encode()).decode()


def decrypt_real_name(encrypted: str) -> str:
    """解密真实姓名。cryptography 不可用时直接返回。"""
    if not encrypted:
        return ""
    f = _get_fernet()
    if f is None:
        return encrypted  # 明文回退
    try:
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        return encrypted


def mask_sensitive(text: str, show_chars: int = 1) -> str:
    """脱敏：只显示首个字符，其余用*替换"""
    if not text:
        return ""
    if len(text) <= show_chars:
        return text[0] + "*"
    return text[:show_chars] + "*" * (len(text) - show_chars)


def hash_id(value: str) -> str:
    """对ID做单向哈希"""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


# ============================================================
# 简易权限检查
# ============================================================

ROLE_PERMISSIONS = {
    "admin": {
        "children:read", "children:write", "children:delete", "children:export",
        "meal_plans:read", "meal_plans:write",
        "rules:read", "rules:write",
        "recommend:execute", "recommend:read", "recommend:confirm", "recommend:export",
        "audit:read",
    },
    "teacher": {
        "children:read", "children:write",
        "meal_plans:read",
        "rules:read",
        "recommend:execute", "recommend:read", "recommend:confirm", "recommend:export",
        "audit:read",
    },
    "parent": {
        "recommend:read_own",
    },
    "nutritionist": {
        "children:read",
        "meal_plans:read", "meal_plans:write",
        "rules:read", "rules:write",
        "recommend:read", "recommend:confirm",
        "audit:read",
    },
}


def check_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def require_permission(role: str, permission: str) -> tuple:
    if not check_permission(role, permission):
        return False, f"角色「{role}」无权执行「{permission}」操作"
    return True, ""
