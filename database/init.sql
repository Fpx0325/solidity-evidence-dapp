-- ============================================================
-- Solidity 智能合约存证 DApp - 本地开发数据库初始化
-- 仅用于本机学习演示。部署到共享环境前请修改应用账号密码！
-- 执行方式：mysql -u root -p < database/init.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS evidence_dapp
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 本地开发用账号（密码需与 .env 保持一致；请按需修改）
CREATE USER IF NOT EXISTS 'evidence_app'@'localhost'
  IDENTIFIED BY 'evidence_demo_pwd';
CREATE USER IF NOT EXISTS 'evidence_app'@'127.0.0.1'
  IDENTIFIED BY 'evidence_demo_pwd';

GRANT ALL PRIVILEGES ON evidence_dapp.* TO 'evidence_app'@'localhost';
GRANT ALL PRIVILEGES ON evidence_dapp.* TO 'evidence_app'@'127.0.0.1';
FLUSH PRIVILEGES;

USE evidence_dapp;

-- 文件存证记录：链上关键字段 + 链下业务元数据
CREATE TABLE IF NOT EXISTS evidence_records (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  file_name VARCHAR(255) NOT NULL COMMENT '原始文件名（仅展示，不保存文件内容）',
  file_hash CHAR(64) NOT NULL COMMENT 'SHA-256 十六进制摘要，不含 0x',
  user_name VARCHAR(64) NOT NULL COMMENT '操作人业务标签，非登录身份',
  block_number BIGINT UNSIGNED NOT NULL COMMENT '合约交易所在区块高度',
  tx_hash CHAR(66) NOT NULL COMMENT '交易哈希，含 0x',
  chain_owner VARCHAR(42) NOT NULL COMMENT '链上写入账户',
  chain_timestamp BIGINT UNSIGNED NOT NULL COMMENT '链上区块时间戳（秒）',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '链下记录创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_file_hash (file_hash),
  KEY idx_created_at (created_at),
  KEY idx_user_name (user_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='文件存证链下记录';

-- 用户操作日志：上传、查验等关键动作
CREATE TABLE IF NOT EXISTS operation_logs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  action VARCHAR(20) NOT NULL COMMENT 'upload / verify / query',
  file_name VARCHAR(255) NULL,
  file_hash CHAR(64) NOT NULL,
  user_name VARCHAR(64) NOT NULL,
  result VARCHAR(32) NOT NULL,
  detail VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_hash (file_hash),
  KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户操作审计日志';
