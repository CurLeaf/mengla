"""
告警规则模块

提供：
1. 告警规则定义
2. 告警状态管理
3. 告警触发和冷却机制
4. 告警通知接口
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .config import ALERTING_CONFIG
from .metrics import get_metrics_collector


logger = logging.getLogger("mengla-alerting")


# ==============================================================================
# 告警级别
# ==============================================================================
class AlertLevel(Enum):
    """告警级别"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# ==============================================================================
# 告警数据结构
# ==============================================================================
@dataclass
class Alert:
    """告警记录"""
    rule_name: str
    level: AlertLevel
    message: str
    value: float
    threshold: float
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    notified: bool = False
    
    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "level": self.level.value,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "triggered_at": self.triggered_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notified": self.notified,
            "is_resolved": self.is_resolved,
        }


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    description: str
    level: AlertLevel
    threshold: float
    cooldown: int  # 冷却时间（秒）
    check_func: Callable[[Dict[str, Any]], float]  # 检查函数，返回当前值
    comparison: str = "lt"  # lt: 小于阈值触发, gt: 大于阈值触发
    
    # 状态
    last_triggered: Optional[datetime] = None
    last_value: Optional[float] = None
    is_firing: bool = False
    
    def should_alert(self, current_value: float) -> bool:
        """判断是否应该触发告警"""
        if self.comparison == "lt":
            return current_value < self.threshold
        else:
            return current_value > self.threshold
    
    def is_in_cooldown(self) -> bool:
        """是否在冷却期"""
        if self.last_triggered is None:
            return False
        elapsed = (datetime.utcnow() - self.last_triggered).total_seconds()
        return elapsed < self.cooldown


# ==============================================================================
# 告警管理器
# ==============================================================================
class AlertManager:
    """告警管理器"""
    
    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._lock = asyncio.Lock()
        self._notifiers: List[Callable[[Alert], None]] = []
        
        # 初始化默认规则
        self._init_default_rules()
    
    def _init_default_rules(self) -> None:
        """初始化默认告警规则"""
        for rule_config in ALERTING_CONFIG.get("rules", []):
            self.add_rule(
                name=rule_config["name"],
                description=rule_config.get("description", ""),
                level=AlertLevel(rule_config.get("level", "WARNING")),
                threshold=rule_config["threshold"],
                cooldown=rule_config.get("cooldown", 600),
                check_func=self._get_check_func(rule_config["name"]),
                comparison=rule_config.get("comparison", "lt"),
            )
    
    def _get_check_func(self, rule_name: str) -> Callable[[Dict[str, Any]], float]:
        """获取规则对应的检查函数"""
        check_funcs = {
            "low_success_rate": lambda m: m.get("success_rate", 1.0),
            "critical_success_rate": lambda m: m.get("success_rate", 1.0),
            "high_latency": lambda m: m.get("avg_duration_ms", 0) / 1000,  # 转换为秒
            "low_cache_hit_rate": lambda m: m.get("cache_hit_rate", 1.0),
        }
        return check_funcs.get(rule_name, lambda m: 0.0)
    
    def add_rule(
        self,
        name: str,
        description: str,
        level: AlertLevel,
        threshold: float,
        cooldown: int,
        check_func: Callable[[Dict[str, Any]], float],
        comparison: str = "lt",
    ) -> None:
        """添加告警规则"""
        self._rules[name] = AlertRule(
            name=name,
            description=description,
            level=level,
            threshold=threshold,
            cooldown=cooldown,
            check_func=check_func,
            comparison=comparison,
        )
    
    def add_notifier(self, notifier: Callable[[Alert], None]) -> None:
        """添加告警通知器"""
        self._notifiers.append(notifier)
    
    async def check_all_rules(self) -> List[Alert]:
        """检查所有规则，返回新触发的告警"""
        metrics_collector = get_metrics_collector()
        metrics = await metrics_collector.get_metrics()
        
        new_alerts = []
        
        async with self._lock:
            for rule_name, rule in self._rules.items():
                try:
                    current_value = rule.check_func(metrics)
                    rule.last_value = current_value
                    
                    if rule.should_alert(current_value):
                        # 应该触发告警
                        if not rule.is_firing:
                            # 新告警
                            if not rule.is_in_cooldown():
                                alert = await self._trigger_alert(rule, current_value)
                                new_alerts.append(alert)
                    else:
                        # 告警恢复
                        if rule.is_firing:
                            await self._resolve_alert(rule_name)
                            
                except Exception as e:
                    logger.warning(f"Error checking rule {rule_name}: {e}")
        
        return new_alerts
    
    async def _trigger_alert(self, rule: AlertRule, current_value: float) -> Alert:
        """触发告警"""
        now = datetime.utcnow()
        
        alert = Alert(
            rule_name=rule.name,
            level=rule.level,
            message=f"{rule.description}: 当前值 {current_value:.4f}, 阈值 {rule.threshold:.4f}",
            value=current_value,
            threshold=rule.threshold,
            triggered_at=now,
        )
        
        rule.is_firing = True
        rule.last_triggered = now
        
        self._active_alerts[rule.name] = alert
        self._alert_history.append(alert)
        
        logger.warning(
            "Alert triggered: %s [%s] - %s",
            rule.name, rule.level.value, alert.message
        )
        
        # 发送通知
        await self._notify(alert)
        
        return alert
    
    async def _resolve_alert(self, rule_name: str) -> None:
        """解除告警"""
        if rule_name not in self._active_alerts:
            return
        
        alert = self._active_alerts.pop(rule_name)
        alert.resolved_at = datetime.utcnow()
        
        if rule_name in self._rules:
            self._rules[rule_name].is_firing = False
        
        logger.info("Alert resolved: %s", rule_name)
    
    async def _notify(self, alert: Alert) -> None:
        """发送告警通知"""
        for notifier in self._notifiers:
            try:
                if asyncio.iscoroutinefunction(notifier):
                    await notifier(alert)
                else:
                    notifier(alert)
                alert.notified = True
            except Exception as e:
                logger.warning(f"Notifier error: {e}")
    
    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """获取当前活跃告警"""
        async with self._lock:
            return [a.to_dict() for a in self._active_alerts.values()]
    
    async def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警历史"""
        async with self._lock:
            return [a.to_dict() for a in self._alert_history[-limit:]]
    
    async def get_rule_status(self) -> List[Dict[str, Any]]:
        """获取规则状态"""
        async with self._lock:
            return [
                {
                    "name": r.name,
                    "description": r.description,
                    "level": r.level.value,
                    "threshold": r.threshold,
                    "cooldown": r.cooldown,
                    "comparison": r.comparison,
                    "is_firing": r.is_firing,
                    "last_triggered": r.last_triggered.isoformat() if r.last_triggered else None,
                    "last_value": r.last_value,
                }
                for r in self._rules.values()
            ]
    
    async def silence_rule(self, rule_name: str, duration_minutes: int = 60) -> bool:
        """静默某个规则"""
        async with self._lock:
            if rule_name not in self._rules:
                return False
            
            rule = self._rules[rule_name]
            # 设置 last_triggered 为未来时间，实现静默效果
            rule.last_triggered = datetime.utcnow() + timedelta(minutes=duration_minutes)
            logger.info("Rule %s silenced for %d minutes", rule_name, duration_minutes)
            return True
    
    async def acknowledge_alert(self, rule_name: str) -> bool:
        """确认告警"""
        async with self._lock:
            if rule_name not in self._active_alerts:
                return False
            
            alert = self._active_alerts[rule_name]
            logger.info("Alert acknowledged: %s", rule_name)
            return True


# ==============================================================================
# 全局告警管理器
# ==============================================================================
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """获取告警管理器（单例）"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


# ==============================================================================
# 告警检查任务
# ==============================================================================
async def run_alert_check() -> List[Dict[str, Any]]:
    """运行告警检查（可定时调用）"""
    manager = get_alert_manager()
    new_alerts = await manager.check_all_rules()
    return [a.to_dict() for a in new_alerts]


# ==============================================================================
# 内置通知器
# ==============================================================================
def log_notifier(alert: Alert) -> None:
    """日志通知器"""
    level_map = {
        AlertLevel.INFO: logger.info,
        AlertLevel.WARNING: logger.warning,
        AlertLevel.CRITICAL: logger.error,
    }
    log_func = level_map.get(alert.level, logger.warning)
    log_func(
        "[ALERT] %s [%s] %s (value=%.4f, threshold=%.4f)",
        alert.rule_name,
        alert.level.value,
        alert.message,
        alert.value,
        alert.threshold,
    )


# 默认添加日志通知器
def init_default_notifiers() -> None:
    """初始化默认通知器"""
    manager = get_alert_manager()
    manager.add_notifier(log_notifier)
