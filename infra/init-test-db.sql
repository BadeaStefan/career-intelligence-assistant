-- Runs once, on first initialisation of the data volume.
--
-- The test suite runs against a separate database on the same instance so a
-- test run can drop and recreate schema freely without touching whatever you
-- have uploaded into the development database.
CREATE DATABASE career_intel_test;
