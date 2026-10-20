import os


os.environ.setdefault("TRITONSPEND_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./tritonspend-test.db")
