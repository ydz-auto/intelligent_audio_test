# -*- coding: utf-8 -*-
"""系统选项应用服务（INT-620）。

CQRS 边界：
- get_all（读侧）：全量 KV 拉取 = 库中已存行 ∪ 领域默认基线（未落库键回退
  默认、显式写入空值覆盖默认——与前端 use-system-options 按默认值类型安全
  解析的口径一致），读侧不产生写副作用。
- upsert（写侧）：单键 upsert，成功后发布 CONFIG_EVENTS / SYSTEM_OPTION_CHANGED
  （命令侧只写并发布事件；Redis 不可用时降级只打日志不阻塞业务）。
"""
import logging
from typing import Dict

from api_gateway.domain.entities.system_option import (
    SYSTEM_OPTION_DEFAULTS,
    SystemOptionValue,
)
from api_gateway.domain.repositories.system_option_repository import SystemOptionRepository
from api_gateway.domain.repositories.system_option_secret_repository import (
    SystemOptionSecretRepository,
)
from api_gateway.infrastructure import eval_secret_cipher
from api_gateway.infrastructure.system_option_repository import SystemOptionRepositoryImpl
from api_gateway.infrastructure.system_option_secret_repository import (
    SystemOptionSecretRepositoryImpl,
)
from api_gateway.utils.response import error_response, success_response
from shared.config.eval_settings import (
    EVAL_LLM_DIMENSIONS,
    EVAL_OPTION_DEFAULTS,
    EVAL_OPTION_KEYS,
    EVAL_SECRET_KEYS,
    EvalOptionKey,
    llm_model_key,
)
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

logger = logging.getLogger(__name__)

# 邀请码注册选项键（注册门禁与公开策略端点共用，拒绝魔法字符串）
INVITE_CODE_REGISTRATION_KEY = 'auth.invite_code_registration'
INVITE_CODE_KEY = 'auth.invite_code'
# 首页可见性选项键：开启后未登录访问首页跳登录页
HOME_REQUIRE_REGISTRATION_KEY = 'site.home_require_registration'


class SystemOptionService:
    """系统选项应用服务（读侧 Query / 写侧 Command）。"""

    _repo: SystemOptionRepository = SystemOptionRepositoryImpl()
    _secret_repo: SystemOptionSecretRepository = SystemOptionSecretRepositoryImpl()

    @classmethod
    def get_all(cls):
        """全量 KV 拉取（读侧）：已存行 ∪ 领域默认基线。"""
        try:
            stored = cls._repo.get_all()
            merged = {**SYSTEM_OPTION_DEFAULTS, **stored}
            return success_response(data=merged)
        except Exception as e:
            logger.warning("读取系统选项失败", exc_info=True)
            return error_response(message=f"读取系统选项失败: {e}")

    @classmethod
    def _read_option(cls, key: str) -> SystemOptionValue:
        """单键读侧（注册门禁等非设置页消费方）：库异常回退领域默认。

        回退默认而非抛错：邀请码门禁是附加约束，KV 读失败不应连带打死
        注册主流程（注册本身仍由 auth_service 落库）。
        """
        try:
            stored = cls._repo.get_all()
            return stored.get(key, SYSTEM_OPTION_DEFAULTS.get(key))
        except Exception:
            logger.warning("读取系统选项失败 key=%s，回退默认", key, exc_info=True)
            return SYSTEM_OPTION_DEFAULTS.get(key)

    @classmethod
    def is_invite_code_registration_required(cls) -> bool:
        """是否开启邀请码注册（公开策略端点 / 注册门禁共用）。"""
        return bool(cls._read_option(INVITE_CODE_REGISTRATION_KEY))

    @classmethod
    def get_invite_code(cls) -> str:
        """配置的邀请码（仅服务端注册校验使用，禁止经接口下发）。"""
        value = cls._read_option(INVITE_CODE_KEY)
        return value.strip() if isinstance(value, str) else ''

    @classmethod
    def is_home_require_registration(cls) -> bool:
        """首页是否仅注册（登录）用户可见。

        邀请码注册开启时强制生效（与产品口径「邀请码注册 → 首页注册后可见」
        一致），否则按 site.home_require_registration 配置。
        """
        if cls.is_invite_code_registration_required():
            return True
        return bool(cls._read_option(HOME_REQUIRE_REGISTRATION_KEY))

    @classmethod
    def upsert(cls, key: str, value: SystemOptionValue):
        """单键写入（写侧）：upsert 后发布 CONFIG_EVENTS 事件。"""
        try:
            cls._repo.upsert(key, value)
            cls._publish_changed(key)
            return success_response(message="设置已更新")
        except Exception as e:
            logger.warning("写入系统选项失败 key=%s", key, exc_info=True)
            return error_response(message=f"写入系统选项失败: {e}")

    @staticmethod
    def _publish_changed(key: str):
        """CQRS 命令侧发布系统选项变更事件（CONFIG_EVENTS 通道）。"""
        try:
            EventBus().publish(
                EventChannel.CONFIG_EVENTS,
                EventType.SYSTEM_OPTION_CHANGED,
                {'action': 'upsert', 'key': key},
            )
        except Exception as e:
            logger.warning("发布系统选项变更事件失败，降级忽略: %s", e)

    # ------------------------------------------------------------------
    # 评估服务密钥（只存密文 + 掩码；明文仅内部运行时端点按需解密）
    # ------------------------------------------------------------------

    @classmethod
    def get_eval_secret_meta(cls):
        """密钥元信息（掩码/更新时间），供系统设置页展示「已配置」。"""
        try:
            return success_response(data={
                'items': cls._secret_repo.list_meta(),
                'cipherAvailable': eval_secret_cipher.available(),
            })
        except Exception as e:
            logger.warning("读取评估密钥元信息失败", exc_info=True)
            return error_response(message=f"读取评估密钥失败: {e}")

    @classmethod
    def upsert_eval_secret(cls, key: str, value: str, updated_by: int):
        """写入/覆盖评估密钥（明文只进不出：加密后仅回掩码）。"""
        if key not in EVAL_SECRET_KEYS:
            return error_response(message=f"不支持的密钥键: {key}", http_code=400)
        plaintext = (value or '').strip()
        if not plaintext:
            return error_response(message="密钥不能为空", http_code=400)
        try:
            ciphertext, version = eval_secret_cipher.encrypt(key, plaintext)
        except eval_secret_cipher.EvalSecretUnavailable as e:
            return error_response(message=str(e), http_code=503)
        try:
            cls._secret_repo.upsert(
                key, ciphertext, version,
                eval_secret_cipher.mask(plaintext), updated_by)
            # 审计：只记键与操作人，绝不记明文
            logger.info("eval_secret_updated key=%s operator=%s", key, updated_by)
            cls._publish_changed(key)
            return success_response(message="密钥已更新")
        except Exception as e:
            logger.warning("写入评估密钥失败 key=%s", key, exc_info=True)
            return error_response(message=f"写入评估密钥失败: {e}")

    @classmethod
    def get_runtime_eval_config(cls) -> Dict:
        """运行时评估配置（内部端点专用）：普通项覆盖值 + 解密后的密钥。

        - 只返回已落库的键（未配置由消费方回落 env / config.yaml）；
        - 密钥解密失败只跳过该键并记 WARNING，不影响其余配置下发。
        """
        stored = cls._repo.get_all()
        model_keys = {llm_model_key(dim) for dim in EVAL_LLM_DIMENSIONS}
        options = {
            key: value for key, value in stored.items()
            if key in EVAL_OPTION_KEYS and key not in model_keys
        }
        dimension_models = {
            dim: stored[llm_model_key(dim)]
            for dim in EVAL_LLM_DIMENSIONS
            if stored.get(llm_model_key(dim))
        }
        secrets: Dict[str, str] = {}
        for key in EVAL_SECRET_KEYS:
            try:
                row = cls._secret_repo.get_ciphertext(key)
                if not row:
                    continue
                secrets[key] = eval_secret_cipher.decrypt(
                    key, row['ciphertext'], row.get('key_version', 1))
            except Exception as e:
                logger.warning("评估密钥解密失败，已跳过 key=%s: %s", key, e)
        return {
            'options': options,
            'secrets': secrets,
            'dimensionModels': dimension_models,
            'defaults': dict(EVAL_OPTION_DEFAULTS),
            'keys': {
                name: key.value for name, key in (
                    ('llmApiBase', EvalOptionKey.LLM_API_BASE),
                    ('llmApiKey', EvalOptionKey.LLM_API_KEY),
                    ('llmDefaultModel', EvalOptionKey.LLM_DEFAULT_MODEL),
                    ('llmMaxTokens', EvalOptionKey.LLM_MAX_TOKENS),
                    ('llmTemperature', EvalOptionKey.LLM_TEMPERATURE),
                    ('llmTimeout', EvalOptionKey.LLM_TIMEOUT),
                    ('llmAudioCompress', EvalOptionKey.LLM_AUDIO_COMPRESS),
                    ('asrUrl', EvalOptionKey.ASR_URL),
                    ('asrTimeout', EvalOptionKey.ASR_TIMEOUT),
                    ('relaySelfZone', EvalOptionKey.RELAY_SELF_ZONE),
                    ('relayHubZone', EvalOptionKey.RELAY_HUB_ZONE),
                    ('relaySyncBackZone', EvalOptionKey.RELAY_SYNC_BACK_ZONE),
                    ('relayTriggerEnabled', EvalOptionKey.RELAY_TRIGGER_ENABLED),
                    ('relayCApiBaseUrl', EvalOptionKey.RELAY_C_API_BASE_URL),
                    ('relayFallbackUrls', EvalOptionKey.RELAY_FALLBACK_URLS),
                    ('relayTokenAB', EvalOptionKey.RELAY_TOKEN_A_B),
                    ('relayTokenBC', EvalOptionKey.RELAY_TOKEN_B_C),
                )
            },
        }
