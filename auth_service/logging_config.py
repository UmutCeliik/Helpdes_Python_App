import logging
import sys
import time  # EKLENDİ
import uuid
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Her istek için benzersiz bir ID tutacak context değişkeni
request_id_var: ContextVar[str] = ContextVar("request_id", default=None)


class RequestIdJsonFormatter(jsonlogger.JsonFormatter):
    """
    Log kayıtlarına request_id'yi ve diğer standart alanları otomatik olarak ekleyen custom formatter.
    """
    def add_fields(self, log_record, record, message_dict):
        # Temel formatı uygula
        super().add_fields(log_record, record, message_dict)
        
        # Standart alanları yeniden adlandır ve yapılandır
        log_record['timestamp'] = log_record.pop('asctime', None) or self.formatTime(record, self.datefmt)
        log_record['level'] = record.levelname
        log_record['service_name'] = record.name
        log_record.pop('levelname', None)
        log_record.pop('name', None)

        # Mesajı ana seviyeye taşı
        if 'message' not in log_record:
             log_record['message'] = record.getMessage()

        # Context'ten request_id'yi al ve log kaydına ekle
        request_id = request_id_var.get()
        if request_id:
            log_record['request_id'] = request_id
        
        # Ekstra bilgileri (örneğin HTTP detayları) 'extra' anahtarı altına taşı
        if 'extra' in log_record:
            log_record.update(log_record.pop('extra'))


def setup_logging(service_name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Uygulama için yapılandırılmış JSON loglamayı ayarlar.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level.upper())
    logger.propagate = False

    if logger.hasHandlers():
        logger.handlers.clear()

    log_handler = logging.StreamHandler(sys.stdout)
    
    # Format string'i daha basit hale getirildi, çünkü alanlar formatlayıcıda manuel olarak ekleniyor.
    formatter = RequestIdJsonFormatter(
        '%(asctime)s'
    )
    log_handler.setFormatter(formatter)
    
    logger.addHandler(log_handler)
    
    # Başlangıç logunu standart print ile yapalım ki logger hazır olmadan önce görünsün.
    print(f"Structured JSON logging configured for service: {service_name} at level: {log_level}")
    
    return logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Gelen her isteğe bir request_id atayan ve istek/yanıt bilgilerini loglayan middleware.
    """
    def __init__(self, app, logger: logging.Logger):
        super().__init__(app)
        self.logger = logger

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)

        start_time = time.time()
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            response.headers["X-Request-ID"] = request_id

            self.logger.info(
                "Request handled successfully",
                extra={
                    "http": {
                        "method": request.method,
                        "url": str(request.url),
                        "path": request.url.path,
                        "query": request.url.query,
                        "client_ip": request.client.host,
                        "status_code": response.status_code,
                        "process_time_ms": int(process_time * 1000)
                    }
                }
            )
        except Exception as e:
            process_time = time.time() - start_time
            self.logger.exception(
                "An unhandled error occurred during request processing",
                extra={
                    "http": {
                        "method": request.method,
                        "url": str(request.url),
                        "path": request.url.path,
                        "query": request.url.query,
                        "client_ip": request.client.host,
                        "status_code": 500,
                        "process_time_ms": int(process_time * 1000)
                    },
                    "error": {
                        "type": type(e).__name__,
                        "message": str(e)
                    }
                }
            )
            # Hatanın yukarıya doğru yayılmasını sağlamak için yeniden fırlat
            raise e
            
        return response