#!/usr/bin/env python3
"""
Cliente do Orquestrador para Instâncias de Fingerprinting

Este módulo fornece uma interface para as instâncias se comunicarem
com o orquestrador central de distribuição de streams.

VERSÃO ATUALIZADA: Integração com novo sistema de API endpoints
Compatível com orchestrator v1.0.0 com endpoints /api/*

Autor: Sistema de Fingerprinting
Data: 2024
"""

import asyncio
import json
import logging
import os
import socket
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

# Import psutil for system metrics
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning(
        "psutil não está disponível. Métricas de sistema não serão coletadas."
    )

logger = logging.getLogger(__name__)


class OrchestratorClient:
    """Cliente para comunicação com o orquestrador central."""

    def __init__(self, orchestrator_url: str, server_id: str, max_streams: int = 20):
        """
        Inicializa o cliente do orquestrador.

        Args:
            orchestrator_url: URL base do orquestrador (ex: http://localhost:8001)
            server_id: ID único desta instância
            max_streams: Número máximo de streams que esta instância pode processar
        """
        self.orchestrator_url = orchestrator_url.rstrip("/")
        self.server_id = server_id
        self.max_streams = max_streams
        self.current_streams = 0
        self.assigned_streams: List[int] = []
        self.is_registered = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.start_time = time.time()  # Para métricas de uptime

        # Detectar IP e porta local
        self.local_ip = self._get_local_ip()
        self.local_port = int(os.getenv("LOCAL_PORT", 8000))

        # Controle de sincronização
        self.last_consistency_check = 0
        self.consistency_check_interval = (
            30  # Verificar consistência a cada 30 segundos
        )
        self.sync_failures = 0
        self.max_sync_failures = 3  # Máximo de falhas antes de tentar re-registro

        # Sistema de alertas proativos
        self.alert_history = deque(maxlen=100)  # Histórico dos últimos 100 alertas
        self.error_patterns = deque(maxlen=50)  # Padrões de erro dos últimos 50 eventos
        self.last_alert_time = {}
        self.alert_cooldown = 300  # 5 minutos entre alertas do mesmo tipo
        self.consecutive_failures = 0
        self.failure_threshold = 5  # Alertar após 5 falhas consecutivas

        logger.info(
            f"Cliente do orquestrador inicializado - Server ID: {self.server_id}, Max Streams: {self.max_streams}"
        )

    @classmethod
    def from_env(cls, server_id: Optional[str] = None):
        """
        Cria cliente do orquestrador a partir de variáveis de ambiente.
        Compatível com configuração existente do FingerV7.
        """
        orchestrator_url = os.getenv("ORCHESTRATOR_URL")
        if not orchestrator_url:
            raise ValueError("ORCHESTRATOR_URL não definida nas variáveis de ambiente")

        if not server_id:
            server_id = (
                os.getenv("INSTANCE_ID")
                or os.getenv("SERVER_ID")
                or f"fingerv7-{int(time.time())}"
            )

        max_streams = int(os.getenv("WORKER_CAPACITY", os.getenv("MAX_STREAMS", "20")))

        return cls(orchestrator_url, server_id, max_streams)

    def _get_local_ip(self) -> str:
        """Detecta o IP local da máquina."""
        try:
            # Conectar a um endereço externo para descobrir IP local
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Obtém ou cria uma sessão HTTP."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def _make_request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Faz uma requisição HTTP para o orquestrador."""
        url = f"{self.orchestrator_url}{endpoint}"
        session = await self._get_session()

        try:
            async with session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Erro na requisição {method} {url}: {response.status} - {error_text}"
                    )
                    raise Exception(f"HTTP {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            logger.error(f"Erro de conexão com orquestrador: {e}")
            raise Exception(f"Erro de conexão: {e}")

    async def register(self) -> bool:
        """Registra esta instância no orquestrador usando nova API."""
        try:
            data = {
                "instance_id": self.server_id,  # Novo formato da API
                "worker_type": "fingerv7",
                "capacity": self.max_streams,
                "status": "active",
                "metadata": {
                    "version": "7.0",
                    "ip": self.local_ip,
                    "port": self.local_port,
                    "capabilities": [
                        "stream_processing",
                        "fingerprinting",
                        "audio_analysis",
                    ],
                    "region": os.getenv("WORKER_REGION", "default"),
                },
            }

            response = await self._make_request("POST", "/api/workers/register", data)

            if response.get("success"):
                self.is_registered = True
                logger.info(
                    f"Instância {self.server_id} registrada com sucesso no orquestrador"
                )
                return True
            else:
                logger.error(f"Falha ao registrar instância: {response}")
                return False

        except Exception as e:
            logger.error(f"Erro ao registrar instância: {e}")
            return False

    def _collect_system_metrics(self) -> Optional[Dict[str, Any]]:
        """Coleta métricas de sistema usando psutil."""
        if not PSUTIL_AVAILABLE:
            return None

        try:
            # CPU usage (percentage)
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = memory.used / (1024**3)
            memory_total_gb = memory.total / (1024**3)

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent
            disk_free_gb = disk.free / (1024**3)
            disk_total_gb = disk.total / (1024**3)

            # Load average (if available)
            load_average = None
            if hasattr(psutil, "getloadavg"):
                try:
                    load_average = list(psutil.getloadavg())
                except (OSError, AttributeError):
                    pass

            # System uptime
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_percent": round(memory_percent, 2),
                "memory_used_gb": round(memory_used_gb, 2),
                "memory_total_gb": round(memory_total_gb, 2),
                "disk_percent": round(disk_percent, 2),
                "disk_free_gb": round(disk_free_gb, 2),
                "disk_total_gb": round(disk_total_gb, 2),
                "load_average": load_average,
                "uptime_seconds": round(uptime_seconds, 2),
            }
        except Exception as e:
            logger.warning(f"Erro ao coletar métricas de sistema: {e}")
            return None

    async def send_heartbeat(self) -> bool:
        """Envia heartbeat para o orquestrador usando nova API."""
        if not self.is_registered:
            logger.warning("Tentativa de enviar heartbeat sem estar registrado")
            return False

        try:
            data = {
                "worker_instance_id": self.server_id,  # Novo formato da API
                "status": "active",
                "current_load": self.current_streams,
                "available_capacity": max(0, self.max_streams - self.current_streams),
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Adicionar métricas de sistema se disponíveis
            system_metrics = self._collect_system_metrics()
            if system_metrics:
                data["metrics"] = {
                    "system": system_metrics,
                    "worker": {
                        "uptime_seconds": int(
                            time.time() - getattr(self, "start_time", time.time())
                        ),
                        "assigned_streams": len(self.assigned_streams),
                        "max_streams": self.max_streams,
                    },
                }

            response = await self._make_request("POST", "/api/heartbeat", data)

            if response.get("success"):
                logger.debug(f"Heartbeat enviado com sucesso para {self.server_id}")
                return True
            else:
                logger.error(f"Falha ao enviar heartbeat: {response}")
                return False

        except Exception as e:
            logger.error(f"Erro ao enviar heartbeat: {e}")
            return False

    async def request_streams(
        self, requested_count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Solicita streams do orquestrador usando nova API."""
        if not self.is_registered:
            logger.warning("Tentativa de solicitar streams sem estar registrado")
            return []

        if requested_count is None:
            requested_count = self.max_streams - self.current_streams

        try:
            # Nova API usa parâmetros GET
            params = {
                "worker_id": self.server_id,
                "capacity": requested_count,
                "worker_type": "fingerv7",
            }

            # Construir URL com parâmetros
            url = f"{self.orchestrator_url}/api/streams/assign"
            session = await self._get_session()

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    result = await response.json()
                    streams = result.get("streams", [])

                    if streams:
                        # Extrair IDs dos streams para compatibilidade
                        new_stream_ids = []
                        for stream in streams:
                            stream_id = stream.get("stream_id") or stream.get("id")
                            if stream_id:
                                new_stream_ids.append(int(stream_id))

                        self.assigned_streams.extend(new_stream_ids)
                        self.current_streams = len(self.assigned_streams)

                        logger.info(
                            f"Recebidos {len(streams)} streams do orquestrador: {new_stream_ids}"
                        )
                        return streams  # Retornar dados completos dos streams
                    else:
                        logger.debug("Nenhum stream disponível no momento")
                        return []

                elif response.status == 404:
                    logger.debug("Worker não encontrado ou nenhum stream disponível")
                    return []
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Erro ao solicitar streams ({response.status}): {error_text}"
                    )
                    return []

        except Exception as e:
            logger.error(f"Erro ao solicitar streams: {e}")
            return []

    async def update_stream_status(
        self, stream_id: int, status: str, result: Optional[Dict] = None
    ) -> bool:
        """Atualiza status de processamento de um stream usando nova API."""
        try:
            data = {
                "stream_id": str(stream_id),
                "worker_instance_id": self.server_id,
                "status": status,
                "result": result or {},
                "timestamp": datetime.utcnow().isoformat(),
            }

            response = await self._make_request("POST", "/api/streams/update", data)

            if response.get("success"):
                logger.debug(f"Status do stream {stream_id} atualizado para {status}")

                # Se completado ou falhou, remover da lista local
                if (
                    status in ["completed", "failed", "cancelled"]
                    and stream_id in self.assigned_streams
                ):
                    self.assigned_streams.remove(stream_id)
                    self.current_streams = len(self.assigned_streams)

                return True
            else:
                logger.error(
                    f"Falha ao atualizar status do stream {stream_id}: {response}"
                )
                return False

        except Exception as e:
            logger.error(f"Erro ao atualizar status do stream {stream_id}: {e}")
            return False

    async def release_streams(self, stream_ids: List[int]) -> bool:
        """Libera streams no orquestrador marcando como cancelled."""
        if not self.is_registered or not stream_ids:
            return True

        try:
            # Usar nova API para marcar streams como cancelled
            success_count = 0
            for stream_id in stream_ids:
                if await self.update_stream_status(stream_id, "cancelled"):
                    success_count += 1

            logger.info(f"Liberados {success_count}/{len(stream_ids)} streams")
            return success_count == len(stream_ids)

        except Exception as e:
            logger.error(f"Erro ao liberar streams: {e}")
            return False

    async def release_all_streams(self) -> bool:
        """Libera todos os streams atribuídos a esta instância."""
        if self.assigned_streams:
            return await self.release_streams(self.assigned_streams.copy())
        return True

    async def get_orchestrator_status(self) -> Optional[Dict[str, Any]]:
        """Obtém status do orquestrador."""
        try:
            response = await self._make_request("GET", "/status")
            return response
        except Exception as e:
            logger.error(f"Erro ao obter status do orquestrador: {e}")
            return None

    async def start_heartbeat_loop(self, interval: int = 60) -> None:
        """Inicia loop de heartbeat em background."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            logger.warning("Loop de heartbeat já está rodando")
            return

        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
        logger.info(f"Loop de heartbeat iniciado com intervalo de {interval}s")

    async def _heartbeat_loop(self, interval: int) -> None:
        """Loop interno de heartbeat."""
        while True:
            try:
                if self.is_registered:
                    success = await self.send_heartbeat()
                    if not success:
                        logger.warning("Falha no heartbeat, tentando re-registrar...")
                        await self.register()
                else:
                    logger.warning("Instância não registrada, tentando registrar...")
                    await self.register()

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info("Loop de heartbeat cancelado")
                break
            except Exception as e:
                logger.error(f"Erro no loop de heartbeat: {e}")
                await asyncio.sleep(
                    min(interval, 30)
                )  # Aguardar menos tempo em caso de erro

    async def stop_heartbeat_loop(self) -> None:
        """Para o loop de heartbeat."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("Loop de heartbeat parado")

    async def shutdown(self) -> None:
        """Encerra o cliente graciosamente."""
        logger.info(f"Encerrando cliente do orquestrador para {self.server_id}")

        # Parar heartbeat
        await self.stop_heartbeat_loop()

        # Liberar todos os streams
        await self.release_all_streams()

        # Fechar sessão HTTP
        if self.session and not self.session.closed:
            await self.session.close()

        logger.info("Cliente do orquestrador encerrado")

    def update_stream_count(self, count: int) -> None:
        """Atualiza o contador local de streams."""
        self.current_streams = count
        logger.debug(f"Contador de streams atualizado para {count}")

    def get_assigned_streams(self) -> List[int]:
        """Retorna lista de streams atribuídos."""
        return self.assigned_streams.copy()

    def is_stream_assigned(self, stream_id: int) -> bool:
        """Verifica se um stream está atribuído a esta instância."""
        return stream_id in self.assigned_streams

    def get_status(self) -> Dict[str, Any]:
        """Retorna status atual do cliente."""
        return {
            "server_id": self.server_id,
            "is_registered": self.is_registered,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "max_streams": self.max_streams,
            "current_streams": self.current_streams,
            "assigned_streams": self.assigned_streams,
            "heartbeat_active": self.heartbeat_task is not None
            and not self.heartbeat_task.done(),
            "sync_failures": getattr(self, "sync_failures", 0),
            "last_consistency_check": getattr(self, "last_consistency_check", 0),
        }

    async def verify_consistency(self) -> Dict[str, Any]:
        """Verifica a consistência entre o estado local e o orquestrador."""
        import time

        current_time = time.time()
        if current_time - self.last_consistency_check < self.consistency_check_interval:
            return {"status": "skipped", "reason": "interval_not_reached"}

        self.last_consistency_check = current_time

        try:
            # Obter status da instância no orquestrador
            response = await self._make_request("GET", f"/instances/{self.server_id}")

            if response.get("status") == "success" and "data" in response:
                orchestrator_data = response["data"]

                # Comparar estados
                local_streams = set(self.assigned_streams)
                orchestrator_streams = set(
                    orchestrator_data.get("assigned_streams", [])
                )

                inconsistencies = {
                    "local_only": list(local_streams - orchestrator_streams),
                    "orchestrator_only": list(orchestrator_streams - local_streams),
                    "current_streams_mismatch": self.current_streams
                    != orchestrator_data.get("current_streams", 0),
                }

                has_inconsistency = (
                    inconsistencies["local_only"]
                    or inconsistencies["orchestrator_only"]
                    or inconsistencies["current_streams_mismatch"]
                )

                if has_inconsistency:
                    logger.warning(
                        f"[CONSISTENCY] Inconsistência detectada: {inconsistencies}"
                    )
                    self.sync_failures += 1

                    # Tentar auto-recuperação
                    if self.sync_failures <= self.max_sync_failures:
                        logger.info(
                            f"[CONSISTENCY] Tentando auto-recuperação ({self.sync_failures}/{self.max_sync_failures})"
                        )
                        await self._auto_recover(orchestrator_data)
                    else:
                        logger.error(
                            f"[CONSISTENCY] Máximo de falhas atingido, necessário re-registro"
                        )
                        await self._force_reregister()

                    return {
                        "status": "inconsistent",
                        "inconsistencies": inconsistencies,
                        "sync_failures": self.sync_failures,
                        "action_taken": (
                            "auto_recovery"
                            if self.sync_failures <= self.max_sync_failures
                            else "force_reregister"
                        ),
                    }
                else:
                    # Reset contador de falhas em caso de sucesso
                    if self.sync_failures > 0:
                        logger.info(
                            f"[CONSISTENCY] Sincronização restaurada, resetando contador de falhas"
                        )
                        self.sync_failures = 0

                    return {
                        "status": "consistent",
                        "local_streams": len(local_streams),
                        "orchestrator_streams": len(orchestrator_streams),
                    }
            else:
                logger.error(
                    f"[CONSISTENCY] Erro ao verificar status no orquestrador: {response}"
                )
                return {"status": "error", "reason": f"orchestrator_response_error"}

        except Exception as e:
            logger.error(f"[CONSISTENCY] Erro durante verificação: {e}")
            return {"status": "error", "reason": str(e)}

    async def _auto_recover(self, orchestrator_data: Dict[str, Any]) -> None:
        """Tenta recuperar automaticamente a sincronização."""
        try:
            # Atualizar estado local com dados do orquestrador
            orchestrator_streams = orchestrator_data.get("assigned_streams", [])
            orchestrator_current = orchestrator_data.get("current_streams", 0)

            logger.info(f"[AUTO_RECOVER] Sincronizando estado local com orquestrador")
            logger.info(
                f"[AUTO_RECOVER] Local: {self.assigned_streams} -> Orquestrador: {orchestrator_streams}"
            )

            self.assigned_streams = orchestrator_streams.copy()
            self.current_streams = orchestrator_current

            logger.info(f"[AUTO_RECOVER] Estado local atualizado com sucesso")

        except Exception as e:
            logger.error(f"[AUTO_RECOVER] Erro durante auto-recuperação: {e}")
            raise

    async def _force_reregister(self) -> None:
        """Força um novo registro no orquestrador."""
        try:
            logger.info(f"[FORCE_REREGISTER] Iniciando re-registro forçado")

            # Resetar estado
            self.is_registered = False
            self.assigned_streams = []
            self.current_streams = 0
            self.sync_failures = 0

            # Tentar novo registro
            success = await self.register()
            if success:
                logger.info(f"[FORCE_REREGISTER] Re-registro bem-sucedido")
            else:
                logger.error(f"[FORCE_REREGISTER] Falha no re-registro")

        except Exception as e:
            logger.error(f"[FORCE_REREGISTER] Erro durante re-registro: {e}")

    async def enhanced_heartbeat(self) -> Dict[str, Any]:
        """Heartbeat aprimorado com verificação de estado de streams."""
        try:
            # Enviar heartbeat normal
            heartbeat_success = await self.send_heartbeat()

            # Registrar resultado da operação de heartbeat
            self.record_operation_result(
                "heartbeat",
                heartbeat_success,
                None if heartbeat_success else "Falha no heartbeat básico",
            )

            if not heartbeat_success:
                return {"status": "heartbeat_failed"}

            # Verificar consistência periodicamente
            consistency_result = await self.verify_consistency()

            # Registrar resultado da verificação de consistência
            consistency_success = consistency_result.get("status") == "consistent"
            self.record_operation_result(
                "consistency_check",
                consistency_success,
                "Inconsistência detectada" if not consistency_success else None,
            )

            return {
                "status": "success",
                "heartbeat": "sent",
                "consistency_check": consistency_result,
            }

        except Exception as e:
            logger.error(f"[ENHANCED_HEARTBEAT] Erro: {e}")
            self.record_operation_result("enhanced_heartbeat", False, str(e))
            return {"status": "error", "reason": str(e)}

    async def run_diagnostic(
        self, local_streams: List[int], local_stream_count: int
    ) -> Dict[str, Any]:
        """
        Executa diagnóstico completo comparando estado local com o orquestrador.

        Args:
            local_streams: Lista de IDs de streams que a instância acredita ter
            local_stream_count: Contagem local de streams

        Returns:
            Dict com resultado detalhado do diagnóstico
        """
        try:
            data = {
                "server_id": self.server_id,
                "local_streams": local_streams,
                "local_stream_count": local_stream_count,
            }

            response = await self._make_request("POST", "/diagnostic", data)

            logger.info(
                f"[DIAGNOSTIC] Diagnóstico executado para {self.server_id}: {response.get('synchronization_status', 'UNKNOWN')}"
            )

            # Log detalhado das inconsistências se houver
            if not response.get("is_synchronized", True):
                inconsistencies = response.get("inconsistencies", {})
                logger.warning(
                    f"[DIAGNOSTIC] Inconsistências detectadas para {self.server_id}:"
                )

                if inconsistencies.get("streams_only_in_local"):
                    logger.warning(
                        f"[DIAGNOSTIC] Streams apenas locais: {inconsistencies['streams_only_in_local']}"
                    )

                if inconsistencies.get("streams_only_in_orchestrator"):
                    logger.warning(
                        f"[DIAGNOSTIC] Streams apenas no orquestrador: {inconsistencies['streams_only_in_orchestrator']}"
                    )

                if inconsistencies.get("count_mismatch"):
                    logger.warning(
                        f"[DIAGNOSTIC] Contagem local ({local_stream_count}) != orquestrador ({response.get('orchestrator_state', {}).get('stream_count', 0)})"
                    )

                recommendations = response.get("recommendations", [])
                if recommendations:
                    logger.info(
                        f"[DIAGNOSTIC] Recomendações: {'; '.join(recommendations)}"
                    )

            return response

        except Exception as e:
            logger.error(
                f"[DIAGNOSTIC] Erro ao executar diagnóstico para {self.server_id}: {e}"
            )
            return {
                "server_id": self.server_id,
                "error": str(e),
                "is_synchronized": False,
                "synchronization_status": "ERROR",
            }

    def _record_alert(
        self, alert_type: str, message: str, severity: str = "WARNING"
    ) -> None:
        """
        Registra um alerta no histórico para análise de padrões.

        Args:
            alert_type: Tipo do alerta (e.g., 'SYNC_FAILURE', 'CONNECTION_ERROR')
            message: Mensagem detalhada do alerta
            severity: Severidade do alerta ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
        """
        alert = {
            "timestamp": datetime.now(),
            "type": alert_type,
            "message": message,
            "severity": severity,
            "server_id": self.server_id,
        }

        self.alert_history.append(alert)

        # Log do alerta
        log_level = getattr(logging, severity, logging.WARNING)
        logger.log(log_level, f"[ALERT-{alert_type}] {message}")

    def _should_send_alert(self, alert_type: str) -> bool:
        """
        Verifica se um alerta deve ser enviado baseado no cooldown.

        Args:
            alert_type: Tipo do alerta

        Returns:
            True se o alerta deve ser enviado
        """
        current_time = time.time()
        last_alert = self.last_alert_time.get(alert_type, 0)

        if current_time - last_alert >= self.alert_cooldown:
            self.last_alert_time[alert_type] = current_time
            return True

        return False

    def _analyze_error_patterns(self) -> List[Dict[str, Any]]:
        """
        Analisa padrões de erro no histórico de alertas.

        Returns:
            Lista de padrões detectados
        """
        patterns = []

        if len(self.alert_history) < 5:
            return patterns

        # Analisar últimos 30 minutos
        cutoff_time = datetime.now() - timedelta(minutes=30)
        recent_alerts = [
            alert for alert in self.alert_history if alert["timestamp"] > cutoff_time
        ]

        if len(recent_alerts) >= 5:
            patterns.append(
                {
                    "type": "HIGH_FREQUENCY_ALERTS",
                    "description": f"{len(recent_alerts)} alertas nos últimos 30 minutos",
                    "severity": "WARNING",
                    "recommendation": "Investigar causa raiz dos problemas frequentes",
                }
            )

        # Analisar tipos de erro mais comuns
        error_types = {}
        for alert in recent_alerts:
            alert_type = alert["type"]
            error_types[alert_type] = error_types.get(alert_type, 0) + 1

        for error_type, count in error_types.items():
            if count >= 3:
                patterns.append(
                    {
                        "type": "RECURRING_ERROR",
                        "description": f"Erro {error_type} ocorreu {count} vezes recentemente",
                        "severity": "ERROR",
                        "recommendation": f"Investigar problema específico com {error_type}",
                    }
                )

        return patterns

    def _check_proactive_alerts(self) -> None:
        """
        Verifica condições para alertas proativos.
        """
        try:
            # Verificar falhas consecutivas
            if self.consecutive_failures >= self.failure_threshold:
                if self._should_send_alert("CONSECUTIVE_FAILURES"):
                    self._record_alert(
                        "CONSECUTIVE_FAILURES",
                        f"{self.consecutive_failures} falhas consecutivas detectadas para {self.server_id}",
                        "ERROR",
                    )

            # Analisar padrões de erro
            patterns = self._analyze_error_patterns()
            for pattern in patterns:
                if self._should_send_alert(pattern["type"]):
                    self._record_alert(
                        pattern["type"],
                        f"{pattern['description']} - {pattern['recommendation']}",
                        pattern["severity"],
                    )

            # Verificar se há muitos alertas de sincronização
            sync_alerts = [
                alert
                for alert in self.alert_history
                if "SYNC" in alert["type"]
                and alert["timestamp"] > datetime.now() - timedelta(hours=1)
            ]

            if len(sync_alerts) >= 3:
                if self._should_send_alert("SYNC_DEGRADATION"):
                    self._record_alert(
                        "SYNC_DEGRADATION",
                        f"Degradação na sincronização detectada: {len(sync_alerts)} problemas na última hora",
                        "WARNING",
                    )

        except Exception as e:
            logger.error(f"[PROACTIVE_ALERTS] Erro ao verificar alertas proativos: {e}")

    def record_operation_result(
        self, operation: str, success: bool, error_message: str = None
    ) -> None:
        """
        Registra o resultado de uma operação para análise de padrões.

        Args:
            operation: Nome da operação (e.g., 'heartbeat', 'stream_request')
            success: Se a operação foi bem-sucedida
            error_message: Mensagem de erro se aplicável
        """
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

            # Registrar erro no padrão
            error_info = {
                "timestamp": datetime.now(),
                "operation": operation,
                "error": error_message or "Unknown error",
            }
            self.error_patterns.append(error_info)

            # Registrar alerta se necessário
            self._record_alert(
                f"{operation.upper()}_FAILURE",
                f'Falha na operação {operation}: {error_message or "Erro desconhecido"}',
                "ERROR",
            )

        # Verificar alertas proativos
        self._check_proactive_alerts()

    def get_alert_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        Retorna um resumo dos alertas das últimas horas.

        Args:
            hours: Número de horas para analisar

        Returns:
            Resumo dos alertas
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_alerts = [
            alert for alert in self.alert_history if alert["timestamp"] > cutoff_time
        ]

        # Contar por tipo e severidade
        by_type = {}
        by_severity = {}

        for alert in recent_alerts:
            alert_type = alert["type"]
            severity = alert["severity"]

            by_type[alert_type] = by_type.get(alert_type, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1

        return {
            "total_alerts": len(recent_alerts),
            "by_type": by_type,
            "by_severity": by_severity,
            "consecutive_failures": self.consecutive_failures,
            "recent_patterns": self._analyze_error_patterns(),
            "period_hours": hours,
        }


# Função de conveniência para criar cliente
def create_orchestrator_client(
    server_id: Optional[str] = None,
    orchestrator_url: Optional[str] = None,
    max_streams: Optional[int] = None,
) -> OrchestratorClient:
    """Cria um cliente do orquestrador com configurações padrão."""

    if server_id is None:
        server_id = os.getenv("SERVER_ID", socket.gethostname())

    if orchestrator_url is None:
        orchestrator_host = os.getenv("ORCHESTRATOR_HOST", "localhost")
        orchestrator_port = os.getenv("ORCHESTRATOR_PORT", "8001")
        orchestrator_url = f"http://{orchestrator_host}:{orchestrator_port}"

    if max_streams is None:
        max_streams = int(os.getenv("MAX_STREAMS_PER_INSTANCE", 20))

    return OrchestratorClient(orchestrator_url, server_id, max_streams)


# Exemplo de uso
if __name__ == "__main__":
    import sys

    async def test_client():
        """Teste básico do cliente."""
        client = create_orchestrator_client()

        try:
            # Registrar
            if await client.register():
                print(f"Registrado como {client.server_id}")

                # Iniciar heartbeat
                await client.start_heartbeat_loop(30)

                # Solicitar streams
                streams = await client.request_streams(5)
                print(f"Streams recebidos: {streams}")

                # Aguardar um pouco
                await asyncio.sleep(10)

                # Status
                status = await client.get_orchestrator_status()
                print(f"Status do orquestrador: {status}")

                # Liberar streams
                if streams:
                    await client.release_streams(streams[:2])
                    print(f"Liberados 2 streams")

            else:
                print("Falha ao registrar")

        except KeyboardInterrupt:
            print("\nEncerrando...")
        finally:
            await client.shutdown()

    # Configurar logging
    logging.basicConfig(level=logging.INFO)

    # Executar teste
    asyncio.run(test_client())
