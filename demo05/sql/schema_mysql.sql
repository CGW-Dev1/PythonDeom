CREATE DATABASE IF NOT EXISTS rent_analysis
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE rent_analysis;

CREATE TABLE IF NOT EXISTS users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rent_listings (
  id INT PRIMARY KEY AUTO_INCREMENT,
  source VARCHAR(50) NOT NULL DEFAULT 'unknown',
  source_id VARCHAR(120),
  detail_url VARCHAR(500),
  district VARCHAR(80) NOT NULL,
  community VARCHAR(160) NOT NULL,
  rent_price DOUBLE NOT NULL,
  area DOUBLE NOT NULL,
  house_type VARCHAR(80) NOT NULL,
  orientation VARCHAR(80),
  floor VARCHAR(80),
  tags VARCHAR(500),
  publish_time VARCHAR(80),
  unit_price DOUBLE,
  raw_hash VARCHAR(64) NOT NULL,
  crawled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_listing_raw_hash (raw_hash),
  INDEX ix_rent_listings_district (district),
  INDEX ix_rent_listings_community (community),
  INDEX ix_rent_listings_house_type (house_type),
  INDEX ix_rent_listings_rent_price (rent_price),
  INDEX ix_listing_filter (district, house_type, rent_price)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
