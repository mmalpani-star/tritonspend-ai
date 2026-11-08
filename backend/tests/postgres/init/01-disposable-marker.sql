-- Runs once, when compose.postgres-test.yml initializes an empty data directory.
-- backend/tests/test_postgres_integration.py requires this exact comment before
-- any write, so a database that was not provisioned this way is refused.
COMMENT ON DATABASE tritonspend_test IS 'tritonspend-disposable-test';
