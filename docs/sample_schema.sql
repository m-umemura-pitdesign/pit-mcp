-- =====================================================
-- 駐車場管理システム サンプルスキーマ
-- テスト・開発用
-- =====================================================

-- データベース作成
CREATE DATABASE IF NOT EXISTS parking_system
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE parking_system;

-- =====================================================
-- テーブル定義
-- =====================================================

-- 駐車場マスターテーブル
CREATE TABLE IF NOT EXISTS parkings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT '駐車場名',
    code VARCHAR(50) NOT NULL UNIQUE COMMENT '駐車場コード',
    address VARCHAR(500) COMMENT '住所',
    capacity INT COMMENT '収容台数',
    status ENUM('active', 'inactive', 'maintenance') DEFAULT 'active' COMMENT '稼働状態',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_code (code),
    INDEX idx_status (status)
) ENGINE=InnoDB COMMENT='駐車場マスター';

-- 駐車場設定テーブル
CREATE TABLE IF NOT EXISTS parking_configs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    parking_id BIGINT NOT NULL COMMENT '駐車場ID',
    re_charge_grace_time INT COMMENT '再課金猶予時間（分）- NULLの場合はデフォルト使用',
    default_re_charge_time INT NOT NULL DEFAULT 30 COMMENT 'デフォルト再課金猶予時間（分）',
    max_daily_charge INT COMMENT '1日最大料金（円）- NULLは上限なし',
    night_rate_enabled BOOLEAN DEFAULT FALSE COMMENT '夜間料金適用フラグ',
    night_rate_start_time TIME COMMENT '夜間料金開始時刻',
    night_rate_end_time TIME COMMENT '夜間料金終了時刻',
    night_rate_amount INT COMMENT '夜間料金（円）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parking_id) REFERENCES parkings(id) ON DELETE CASCADE,
    UNIQUE INDEX idx_parking_id (parking_id)
) ENGINE=InnoDB COMMENT='駐車場課金設定';

-- 駐車料金テーブル
CREATE TABLE IF NOT EXISTS parking_rates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    parking_id BIGINT NOT NULL COMMENT '駐車場ID',
    day_type ENUM('weekday', 'weekend', 'holiday') NOT NULL COMMENT '曜日種別',
    start_time TIME NOT NULL COMMENT '適用開始時刻',
    end_time TIME NOT NULL COMMENT '適用終了時刻',
    rate_per_unit INT NOT NULL COMMENT '単位時間あたり料金（円）',
    unit_minutes INT NOT NULL DEFAULT 30 COMMENT '課金単位（分）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parking_id) REFERENCES parkings(id) ON DELETE CASCADE,
    INDEX idx_parking_day (parking_id, day_type)
) ENGINE=InnoDB COMMENT='駐車料金';

-- 駐車セッション（入出庫履歴）テーブル
CREATE TABLE IF NOT EXISTS parking_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    parking_id BIGINT NOT NULL COMMENT '駐車場ID',
    vehicle_number VARCHAR(20) NOT NULL COMMENT '車両番号',
    entry_time DATETIME NOT NULL COMMENT '入庫日時',
    exit_time DATETIME COMMENT '出庫日時 - NULLは駐車中',
    charged_amount INT DEFAULT 0 COMMENT '請求金額（円）',
    payment_status ENUM('pending', 'paid', 'failed') DEFAULT 'pending' COMMENT '支払状態',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parking_id) REFERENCES parkings(id) ON DELETE CASCADE,
    INDEX idx_parking_entry (parking_id, entry_time),
    INDEX idx_vehicle (vehicle_number),
    INDEX idx_payment_status (payment_status)
) ENGINE=InnoDB COMMENT='駐車セッション';

-- =====================================================
-- サンプルデータ
-- =====================================================

-- 駐車場マスター
INSERT INTO parkings (name, code, address, capacity, status) VALUES
('東京中央パーキング', 'TKY001', '東京都中央区日本橋1-1-1', 100, 'active'),
('新宿西口パーキング', 'SJK002', '東京都新宿区西新宿2-2-2', 200, 'active'),
('渋谷駅前パーキング', 'SBY003', '東京都渋谷区道玄坂1-1-1', 150, 'active'),
('池袋東口パーキング', 'IKB004', '東京都豊島区東池袋1-1-1', 80, 'active'),
('品川シーサイドパーキング', 'SGW005', '東京都品川区東品川4-4-4', 300, 'active'),
('横浜みなとみらいパーキング', 'YKH006', '神奈川県横浜市西区みなとみらい1-1-1', 500, 'active'),
('大阪梅田パーキング', 'OSK007', '大阪府大阪市北区梅田1-1-1', 400, 'active'),
('メンテナンス中駐車場', 'MNT008', '東京都千代田区丸の内1-1-1', 50, 'maintenance');

-- 駐車場設定
INSERT INTO parking_configs (parking_id, re_charge_grace_time, default_re_charge_time, max_daily_charge, night_rate_enabled, night_rate_start_time, night_rate_end_time, night_rate_amount) VALUES
-- 東京中央: デフォルト設定（re_charge_grace_time = NULL）
(1, NULL, 30, 1800, TRUE, '22:00:00', '06:00:00', 600),
-- 新宿西口: 個別設定（60分の猶予）
(2, 60, 30, 2000, TRUE, '23:00:00', '07:00:00', 400),
-- 渋谷駅前: 個別設定（45分の猶予）、夜間料金あり
(3, 45, 30, 1800, TRUE, '22:00:00', '08:00:00', 500),
-- 池袋東口: デフォルト設定、夜間料金なし
(4, NULL, 30, 1500, FALSE, NULL, NULL, NULL),
-- 品川シーサイド: デフォルト設定、最大料金なし
(5, NULL, 30, NULL, TRUE, '21:00:00', '07:00:00', 800),
-- 横浜みなとみらい: 個別設定（90分の猶予）
(6, 90, 30, 2500, TRUE, '22:00:00', '08:00:00', 700),
-- 大阪梅田: 個別設定（20分の猶予 - 短め）
(7, 20, 30, 2000, TRUE, '23:00:00', '06:00:00', 500),
-- メンテナンス中: デフォルト設定
(8, NULL, 30, 1000, FALSE, NULL, NULL, NULL);

-- 駐車料金（サンプル: 東京中央パーキング）
INSERT INTO parking_rates (parking_id, day_type, start_time, end_time, rate_per_unit, unit_minutes) VALUES
-- 東京中央: 平日
(1, 'weekday', '08:00:00', '22:00:00', 300, 30),
(1, 'weekday', '22:00:00', '08:00:00', 100, 60),
-- 東京中央: 土日
(1, 'weekend', '08:00:00', '22:00:00', 400, 30),
(1, 'weekend', '22:00:00', '08:00:00', 100, 60),
-- 渋谷駅前: 平日
(3, 'weekday', '08:00:00', '22:00:00', 400, 20),
(3, 'weekday', '22:00:00', '08:00:00', 100, 60),
-- 渋谷駅前: 土日
(3, 'weekend', '08:00:00', '22:00:00', 500, 20),
(3, 'weekend', '22:00:00', '08:00:00', 100, 60);

-- 駐車セッション（サンプルデータ）
INSERT INTO parking_sessions (parking_id, vehicle_number, entry_time, exit_time, charged_amount, payment_status) VALUES
-- 東京中央パーキング
(1, '品川 300 あ 1234', '2024-01-15 09:00:00', '2024-01-15 12:30:00', 2100, 'paid'),
(1, '練馬 500 い 5678', '2024-01-15 10:30:00', '2024-01-15 14:00:00', 2100, 'paid'),
(1, '足立 300 う 9012', '2024-01-15 14:00:00', NULL, 0, 'pending'),  -- 現在駐車中
-- 渋谷駅前パーキング
(3, '世田谷 400 え 3456', '2024-01-15 08:00:00', '2024-01-15 10:00:00', 2400, 'paid'),
(3, '目黒 300 お 7890', '2024-01-15 11:00:00', NULL, 0, 'pending');  -- 現在駐車中

-- =====================================================
-- 読み取り専用ユーザーの作成
-- =====================================================

-- ユーザー作成（パスワードは環境に応じて変更すること）
-- CREATE USER 'mcp_readonly'@'%' IDENTIFIED BY 'your_secure_password_here';

-- SELECT権限のみ付与
-- GRANT SELECT ON parking_system.parkings TO 'mcp_readonly'@'%';
-- GRANT SELECT ON parking_system.parking_configs TO 'mcp_readonly'@'%';
-- GRANT SELECT ON parking_system.parking_rates TO 'mcp_readonly'@'%';
-- GRANT SELECT ON parking_system.parking_sessions TO 'mcp_readonly'@'%';

-- FLUSH PRIVILEGES;

-- =====================================================
-- 確認用クエリ
-- =====================================================

-- 全駐車場の一覧
-- SELECT id, name, code, status FROM parkings;

-- 再課金猶予時間の確認（デフォルト vs 個別設定）
-- SELECT
--     p.name,
--     pc.re_charge_grace_time,
--     pc.default_re_charge_time,
--     COALESCE(pc.re_charge_grace_time, pc.default_re_charge_time) as effective_time,
--     CASE
--         WHEN pc.re_charge_grace_time IS NULL THEN 'デフォルト'
--         ELSE '個別設定'
--     END as setting_type
-- FROM parkings p
-- JOIN parking_configs pc ON p.id = pc.parking_id
-- ORDER BY p.id;

-- 夜間料金が有効な駐車場
-- SELECT
--     p.name,
--     pc.night_rate_start_time,
--     pc.night_rate_end_time,
--     pc.night_rate_amount
-- FROM parkings p
-- JOIN parking_configs pc ON p.id = pc.parking_id
-- WHERE pc.night_rate_enabled = TRUE
-- ORDER BY p.name;
