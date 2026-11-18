bind = ["0.0.0.0:8888", "0.0.0.0:8080"]
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
graceful_timeout = 15
