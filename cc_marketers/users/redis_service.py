import redis
import requests
import json
import logging
from typing import Any, Optional, Dict, List
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class RedisService:
    """
    Unified Redis service for Django with Upstash support
    Provides both direct Redis operations and Django cache integration
    """
    
    def __init__(self, use_rest_api: bool = False):
        self.use_rest_api = use_rest_api
        self.tcp_client = None
        
        if not use_rest_api:
            self._init_tcp_client()
        else:
            self._init_rest_client()
    
    def _init_tcp_client(self):
        """Initialize TCP Redis client"""
        try:
            self.tcp_client = redis.from_url(
                settings.UPSTASH_REDIS_URL,
                decode_responses=True,
                health_check_interval=30,
                socket_keepalive=True,
                retry_on_timeout=True,
                socket_connect_timeout=10,
                socket_timeout=10,
            )
            self.tcp_client.ping()
            logger.info("✓ Upstash Redis TCP connection established")
        except Exception as e:
            logger.error(f"✗ Failed to connect to Upstash Redis via TCP: {e}")
            self.tcp_client = None
    
    def _init_rest_client(self):
        """Initialize REST API client"""
        self.rest_url = settings.UPSTASH_REDIS_REST_URL
        self.rest_token = settings.UPSTASH_REDIS_REST_TOKEN
        self.readonly_token = getattr(settings, 'UPSTASH_REDIS_READONLY_TOKEN', '')
        
        self.headers = {
            'Authorization': f'Bearer {self.rest_token}',
            'Content-Type': 'application/json'
        }
        
        if self.readonly_token:
            self.readonly_headers = {
                'Authorization': f'Bearer {self.readonly_token}',
                'Content-Type': 'application/json'
            }
        else:
            self.readonly_headers = self.headers
    
    # Core Redis Operations
    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """Set a key-value pair with optional timeout"""
        if timeout is None:
            timeout = getattr(settings, 'REDIS_SERVICE_CONFIG', {}).get('DEFAULT_TIMEOUT', 300)
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            if self.use_rest_api:
                return self._rest_request('set', [key, value, 'EX', timeout])
            else:
                if self.tcp_client:
                    return bool(self.tcp_client.setex(key, timeout, value))
                return False
        except Exception as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key with optional default"""
        try:
            if self.use_rest_api:
                result = self._rest_request('get', [key], readonly=True)
                if result is None:
                    return default
                try:
                    return json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    return result
            else:
                if self.tcp_client:
                    value = self.tcp_client.get(key)
                    if value is None:
                        return default
                    try:
                        return json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        return value
                return default
        except Exception as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return default
    
    def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        try:
            if self.use_rest_api:
                result = self._rest_request('del', list(keys))
                return result if isinstance(result, int) else 0
            else:
                if self.tcp_client:
                    return self.tcp_client.delete(*keys)
                return 0
        except Exception as e:
            logger.error(f"Redis DELETE error for keys {keys}: {e}")
            return 0
    
    def exists(self, *keys: str) -> int:
        """Check if keys exist"""
        try:
            if self.use_rest_api:
                result = self._rest_request('exists', list(keys), readonly=True)
                return result if isinstance(result, int) else 0
            else:
                if self.tcp_client:
                    return self.tcp_client.exists(*keys)
                return 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for keys {keys}: {e}")
            return 0
    
    # Hash Operations
    def hset(self, name: str, mapping: Dict[str, Any]) -> int:
        """Set hash fields"""
        try:
            processed_mapping = {}
            for key, value in mapping.items():
                if isinstance(value, (dict, list)):
                    processed_mapping[key] = json.dumps(value)
                else:
                    processed_mapping[key] = str(value)
            
            if self.use_rest_api:
                args = [name]
                for k, v in processed_mapping.items():
                    args.extend([k, v])
                result = self._rest_request('hset', args)
                return result if isinstance(result, int) else 0
            else:
                if self.tcp_client:
                    return self.tcp_client.hset(name, mapping=processed_mapping)
                return 0
        except Exception as e:
            logger.error(f"Redis HSET error for hash '{name}': {e}")
            return 0
    
    def hget(self, name: str, key: str, default: Any = None) -> Any:
        """Get hash field value"""
        try:
            if self.use_rest_api:
                result = self._rest_request('hget', [name, key], readonly=True)
                if result is None:
                    return default
            else:
                if self.tcp_client:
                    result = self.tcp_client.hget(name, key)
                    if result is None:
                        return default
                else:
                    return default
            
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            logger.error(f"Redis HGET error for hash '{name}', key '{key}': {e}")
            return default
    
    def hgetall(self, name: str) -> Dict[str, Any]:
        """Get all hash fields"""
        try:
            if self.use_rest_api:
                result = self._rest_request('hgetall', [name], readonly=True)
                if not isinstance(result, list):
                    return {}
                # Convert list to dict (Redis returns [key1, val1, key2, val2, ...])
                hash_dict = {}
                for i in range(0, len(result), 2):
                    if i + 1 < len(result):
                        key, value = result[i], result[i + 1]
                        try:
                            hash_dict[key] = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            hash_dict[key] = value
                return hash_dict
            else:
                if self.tcp_client:
                    result = self.tcp_client.hgetall(name)
                    processed_result = {}
                    for key, value in result.items():
                        try:
                            processed_result[key] = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            processed_result[key] = value
                    return processed_result
                return {}
        except Exception as e:
            logger.error(f"Redis HGETALL error for hash '{name}': {e}")
            return {}
    
    # List Operations
    def lpush(self, name: str, *values: Any) -> int:
        """Push values to the left of a list"""
        try:
            processed_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    processed_values.append(json.dumps(value))
                else:
                    processed_values.append(str(value))
            
            if self.use_rest_api:
                result = self._rest_request('lpush', [name] + processed_values)
                return result if isinstance(result, int) else 0
            else:
                if self.tcp_client:
                    return self.tcp_client.lpush(name, *processed_values)
                return 0
        except Exception as e:
            logger.error(f"Redis LPUSH error for list '{name}': {e}")
            return 0
    
    def lrange(self, name: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get a range of elements from a list"""
        try:
            if self.use_rest_api:
                result = self._rest_request('lrange', [name, start, end], readonly=True)
                if not isinstance(result, list):
                    return []
            else:
                if self.tcp_client:
                    result = self.tcp_client.lrange(name, start, end)
                else:
                    return []
            
            processed_result = []
            for item in result:
                try:
                    processed_result.append(json.loads(item))
                except (json.JSONDecodeError, TypeError):
                    processed_result.append(item)
            return processed_result
        except Exception as e:
            logger.error(f"Redis LRANGE error for list '{name}': {e}")
            return []
    
    # Utility Methods
    def ping(self) -> bool:
        """Test Redis connection"""
        try:
            if self.use_rest_api:
                result = self._rest_request('ping', [], readonly=True)
                return result == 'PONG'
            else:
                if self.tcp_client:
                    return self.tcp_client.ping()
                return False
        except Exception as e:
            logger.error(f"Redis PING error: {e}")
            return False
    
    def _rest_request(self, command: str, args: List[Any], readonly: bool = False) -> Any:
        """Make REST API request"""
        try:
            url = f"{self.rest_url}/{command.lower()}"
            headers = self.readonly_headers if readonly and hasattr(self, 'readonly_headers') else self.headers
            
            if command.lower() in ['get', 'exists', 'ping'] and len(args) <= 1:
                if args:
                    url += f"/{args[0]}"
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, json=args, headers=headers, timeout=10)
            
            response.raise_for_status()
            result = response.json()
            return result.get('result')
        except Exception as e:
            logger.error(f"REST API error for {command}: {e}")
            return None

# Application-specific cache methods
class AppCache:
    """High-level cache operations for common app patterns"""
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
        self.config = getattr(settings, 'REDIS_SERVICE_CONFIG', {})
    
    def cache_user_data(self, user_id: int, data: Dict[str, Any]) -> bool:
        """Cache user data with default timeout"""
        timeout = self.config.get('USER_CACHE_TIMEOUT', 3600)
        return self.redis.set(f"user:{user_id}", data, timeout)
    
    def get_user_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get cached user data"""
        return self.redis.get(f"user:{user_id}")
    
    def cache_api_response(self, endpoint: str, params: str, data: Any, timeout: int = 300) -> bool:
        """Cache API response"""
        cache_key = f"api:{endpoint}:{hash(params)}"
        return self.redis.set(cache_key, data, timeout)
    
    def get_cached_api_response(self, endpoint: str, params: str) -> Any:
        """Get cached API response"""
        cache_key = f"api:{endpoint}:{hash(params)}"
        return self.redis.get(cache_key)
    
    def increment_rate_limit(self, identifier: str, window: int = 3600) -> int:
        """Increment rate limit counter"""
        key = f"rate_limit:{identifier}"
        try:
            if self.redis.tcp_client:
                pipe = self.redis.tcp_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, window)
                results = pipe.execute()
                return results[0]
            else:
                # Fallback for REST API (less atomic)
                current = self.redis.get(key, 0)
                if isinstance(current, str):
                    current = int(current)
                new_count = current + 1
                self.redis.set(key, new_count, window)
                return new_count
        except Exception as e:
            logger.error(f"Rate limit increment error: {e}")
            return 999  # Fail open
    
    def get_rate_limit(self, identifier: str) -> int:
        """Get current rate limit count"""
        key = f"rate_limit:{identifier}"
        count = self.redis.get(key, 0)
        return int(count) if isinstance(count, (str, int)) else 0

# Global instances
redis_service = RedisService(use_rest_api=False)  # TCP by default
redis_rest = RedisService(use_rest_api=True)      # REST API
app_cache = AppCache(redis_service)

# Django cache shortcuts (uses django-redis)
def django_cache_set(key: str, value: Any, timeout: Optional[int] = None) -> None:
    """Set value using Django's cache framework"""
    cache.set(key, value, timeout)

def django_cache_get(key: str, default: Any = None) -> Any:
    """Get value using Django's cache framework"""
    return cache.get(key, default)

def django_cache_delete(key: str) -> bool:
    """Delete key using Django's cache framework"""
    return cache.delete(key)