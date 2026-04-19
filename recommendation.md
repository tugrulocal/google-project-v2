# Recommendation

For production deployment, keep the HW2 Hybrid pattern but move its components to managed services incrementally. Preserve the in-memory working set for low-latency search visibility, then replace local snapshot files with durable storage that supports atomic writes and versioned recovery. As traffic grows, isolate crawler workers from API/UI processes so queue pressure does not impact query responsiveness; enforce queue-depth and rate controls at the worker boundary and expose them as operational metrics.

For scale and resilience, transition from local index partitions to a dedicated search backend while keeping the same API contract (`/index` and `/search` triple output). Add centralized observability for crawl rate, queue depth, snapshot health, and recovery time objectives. This keeps architectural continuity with HW2 while enabling safer growth from single-machine localhost to production-grade operations.
