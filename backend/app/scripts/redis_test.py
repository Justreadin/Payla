import redis

r = redis.from_url(
    "rediss://default:ASDKAAImcDFmMTE0ZTE0NWFkMDQ0OTM2YTRjYjczZjc0NDZhNjkyZXAxODM5NA@loved-bream-8394.upstash.io:6379",
    ssl=True
)

print(r.ping())  # Should print True
