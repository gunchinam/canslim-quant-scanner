
"""
config/api_keys.py — API 키 통합 관리 (dotenv 기반)
=====================================================

[FIX 3] 보안 취약점 수정:
  기존: api_config.json에 app_key, app_secret, account_no 등 민감 정보 평문 저장
  수정: .env 파일 + 환경변수로 완전 분리. api_config.json에는 민감 정보 없음.

우선순위:
  1. .env 파일 (python-dotenv 로 로드)
  2. 운영체제 환경변수 (export / 시스템 환경변수)
  3. api_config.json — KIS 민감 키는 여기서 절대 읽지 않음
     단, 비민감 설정(is_mock, dry_run, account_code)만 json에서 보조 읽기 허용.
  4. 빈 문자열 (graceful fallback)

마이그레이션 절차:
  1. .env.example 을 .env 로 복사
  2. .env 에 실제 키 값 입력
  3. api_config.json에서 app_key, app_secret, account_no 제거

사용법:
    from config.api_keys import get_all_keys, inject_env, get_kis_keys
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent

_ENV_SEARCH_PATHS = [
    _ROOT / ".env",
    _ROOT.parent / ".env",
]

_DEFAULT_CONFIG_PATH = _ROOT / "api_config.json"


def _load_dotenv() -> bool:
    """
    .env 파일을 탐색하여 환경변수로 로드.
    python-dotenv 가 없으면 자체 파싱으로 fallback.
    이미 설정된 환경변수는 덮어쓰지 않음 (override=False).
    """
    try:
        from dotenv import load_dotenv
        for p in _ENV_SEARCH_PATHS:
            if p.exists():
                load_dotenv(str(p), override=False)
                logger.debug(f"[APIKeys] .env 로드 (dotenv): {p}")
                return True
        return False
    except ImportError:
        pass  # dotenv 미설치 → 직접 파싱

    for p in _ENV_SEARCH_PATHS:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key and not os.environ.get(key):
                            os.environ[key] = val
                logger.debug(f"[APIKeys] .env 로드 (수동 파싱): {p}")
                return True
            except Exception as e:
                logger.warning(f"[APIKeys] .env 파싱 오류: {e}")
    return False


# 모듈 임포트 시 자동으로 .env 로드
_load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _load_json_cfg(path: Optional[str] = None) -> Dict:
    """api_config.json 로드. 민감 KIS 키는 반환 dict에 포함하지 않음."""
    p = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # [FIX 3] 민감 키 강제 제거
        for sensitive in ("app_key", "app_secret", "account_no"):
            cfg.pop(sensitive, None)
        return cfg
    except Exception as e:
        logger.warning(f"[APIKeys] config 로드 실패: {e}")
        return {}


def get_kis_keys(config_path: Optional[str] = None) -> Dict:
    """
    KIS API 인증 정보 반환.
    우선순위:
      1. 환경변수(또는 .env): KIS_APP_KEY 또는 APP_KEY,
                               KIS_APP_SECRET 또는 APP_SECRET,
                               KIS_ACCOUNT_NO 또는 ACCOUNT_NO,
                               KIS_IS_MOCK 또는 IS_MOCK
      2. api_config.json (UI에서 저장한 경우 — 재시작 후 env 미설정 시 보조)
    """
    cfg = _load_json_cfg(config_path)

    # [FIX] 환경변수 우선, 없으면 api_config.json 보조 읽기.
    # KIS_ 접두어 버전과 단축 버전(APP_KEY, ACCOUNT_NO 등) 모두 지원.
    def _kis_env(mode_env_keys: list[str], env_key: str, env_key_short: str, json_key: str) -> str:
        for mode_env_key in mode_env_keys:
            val = _env(mode_env_key)
            if val:
                return val
        val = _env(env_key) or _env(env_key_short)
        if val:
            return val
        json_val = str(cfg.get(json_key, "")).strip()
        if json_val:
            logger.debug(f"[APIKeys] {env_key} 환경변수 없음 — api_config.json '{json_key}' 보조 사용")
        return json_val

    # is_mock: KIS_IS_MOCK → IS_MOCK → api_config.json → 기본값 True (안전)
    is_mock_raw = _env("KIS_IS_MOCK") or _env("IS_MOCK") or str(cfg.get("is_mock", "true"))
    is_mock = is_mock_raw.strip().lower() not in ("false", "0", "no")
    mode_prefix = "KIS_MOCK" if is_mock else "KIS_REAL"

    return {
        "app_key": _kis_env(
            [f"{mode_prefix}_APP_KEY"],
            "KIS_APP_KEY",
            "APP_KEY",
            "app_key",
        ),
        "app_secret": _kis_env(
            [f"{mode_prefix}_APP_SECRET"],
            "KIS_APP_SECRET",
            "APP_SECRET",
            "app_secret",
        ),
        "account_no": _kis_env(
            [f"{mode_prefix}_ACCOUNT_NO"],
            "KIS_ACCOUNT_NO",
            "ACCOUNT_NO",
            "account_no",
        ),
        "account_code": (
            _env(f"{mode_prefix}_ACCOUNT_CODE")
            or _env("KIS_ACCOUNT_CODE")
            or _env("ACCOUNT_CODE")
            or str(cfg.get("account_code", "01"))
        ),
        "is_mock": is_mock,
    }


def get_keys(config_path: Optional[str] = None) -> Dict[str, str]:
    """네이버 / DART API 키 반환 (하위 호환)."""
    cfg = {}
    try:
        p = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
    except Exception as e:
        logging.getLogger(__name__).warning(f"[api_keys] config 로드 실패: {e}")

    def _resolve(env_key: str, cfg_key: str) -> str:
        val = _env(env_key)
        return val if val else str(cfg.get(cfg_key, "")).strip()

    keys = {
        "naver_client_id":     _resolve("NAVER_CLIENT_ID",    "naver_client_id"),
        "naver_client_secret": _resolve("NAVER_CLIENT_SECRET", "naver_client_secret"),
        "dart_api_key":        _resolve("DART_API_KEY",        "dart_api_key"),
    }

    return keys


def get_all_keys(config_path: Optional[str] = None) -> Dict:
    """전체 키 통합 반환 (KIS + 네이버 + DART + OpenAI + Finnhub + Alpha Vantage)."""
    return {
        **get_kis_keys(config_path),
        **get_keys(config_path),
        "zai_api_key":             _env("ZAI_API_KEY"),
        "OPENAI_API_KEY":          _env("OPENAI_API_KEY"),
        "FINNHUB_API_KEY":         _env("FINNHUB_API_KEY"),
        "ALPHA_VANTAGE_API_KEY":   _env("ALPHA_VANTAGE_API_KEY"),
    }


def inject_env(config_path: Optional[str] = None):
    """
    하위 호환 유지. .env는 모듈 임포트 시 이미 로드됨.
    api_config.json의 네이버/DART 보조 값을 추가 주입 (민감 KIS 키 제외).
    """
    cfg = {}
    try:
        p = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
    except Exception:
        return

    safe_mapping = {
        "ZAI_API_KEY":         cfg.get("zai_api_key", ""),
        "OPENAI_API_KEY":      cfg.get("openai_api_key", ""),
    }
    for env_key, val in safe_mapping.items():
        if val and not os.environ.get(env_key):
            os.environ[env_key] = str(val)
            logger.debug(f"[APIKeys] 보조 환경변수 주입: {env_key}")


def get_masked(key_value: str) -> str:
    """로그용 마스킹: 첫 4자만 표시."""
    if not key_value:
        return "(미설정)"
    return key_value[:4] + "***"


def validate_required_keys(keys: dict) -> None:
    """필수 키 누락 시 명확한 에러 발생."""
    required = ["app_key", "app_secret", "account_no"]
    missing = [k for k in required if not keys.get(k)]
    if missing:
        raise ValueError(
            f"필수 KIS API 키 누락: {missing}\n"
            f".env 파일 또는 환경변수를 확인하세요.\n"
            f"참고: .env.example 파일을 복사해서 .env를 만드세요."
        )


def save_keys(
    naver_client_id:     str = "",
    naver_client_secret: str = "",
    dart_api_key:        str = "",
    config_path: Optional[str] = None,
) -> bool:
    """
    네이버/DART 키를 api_config.json에 저장 (대시보드 설정 화면용).
    KIS 민감 키(app_key, app_secret, account_no)는 저장하지 않음.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    try:
        cfg: Dict = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

        if naver_client_id:
            cfg["naver_client_id"]     = naver_client_id
        if naver_client_secret:
            cfg["naver_client_secret"] = naver_client_secret
        if dart_api_key:
            cfg["dart_api_key"]        = dart_api_key

        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        inject_env(config_path)
        logger.info(f"[APIKeys] API 키 저장 완료: {path}")
        return True
    except Exception as e:
        logger.error(f"[APIKeys] API 키 저장 실패: {e}")
        return False
