-- Runs once when the PostgreSQL container is first created.
-- One database per service (and per hospital node for patients and records).
CREATE DATABASE db_auth;
CREATE DATABASE db_pat_a;
CREATE DATABASE db_pat_b;
CREATE DATABASE db_rec_a;
CREATE DATABASE db_rec_b;
CREATE DATABASE db_refer;
CREATE DATABASE db_dash;
CREATE DATABASE db_audit;
CREATE DATABASE db_gateway;
