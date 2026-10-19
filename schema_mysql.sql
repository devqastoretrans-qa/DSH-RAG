-- =====================================================================
-- Personalized RAG System: MySQL Database Schema
-- Defines users, purchases (courses, books, sessions), and past records
-- =====================================================================

CREATE DATABASE IF NOT EXISTS rag_users CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE rag_users;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Purchases Table (Courses, Books, Sessions)
CREATE TABLE IF NOT EXISTS purchases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    item_type ENUM('course', 'book', 'session', 'consultation') NOT NULL,
    item_title VARCHAR(255) NOT NULL,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_purchases (user_id)
);

-- 3. Past Records Table (Consultations, notes, interaction history)
CREATE TABLE IF NOT EXISTS past_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    interaction_type VARCHAR(100) NOT NULL,
    summary_notes TEXT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_records (user_id)
);

-- =====================================================================
-- Seed Data for Testing & Demonstration
-- =====================================================================

-- John: Primary persona from prompt
INSERT INTO users (id, name, email) VALUES
('john', 'John', 'john@example.com')
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO purchases (user_id, item_type, item_title) VALUES
('john', 'session', '55-minute ADHD session'),
('john', 'book', 'How to Be Calm When Having ADHD')
ON DUPLICATE KEY UPDATE item_title=VALUES(item_title);

-- Sarah: Comparison persona
INSERT INTO users (id, name, email) VALUES
('sarah', 'Sarah', 'sarah@example.com')
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO purchases (user_id, item_type, item_title) VALUES
('sarah', 'course', 'Mindfulness and Deep Focus Workshop'),
('sarah', 'book', 'Atomic Habits for Neurodiverse Minds')
ON DUPLICATE KEY UPDATE item_title=VALUES(item_title);

INSERT INTO past_records (user_id, interaction_type, summary_notes) VALUES
('sarah', 'Coaching Session', 'Discussed developing an energizing morning routine to reduce sensory overload and afternoon focus slump.')
ON DUPLICATE KEY UPDATE summary_notes=VALUES(summary_notes);

-- Guest / Anonymous user with no purchase history
INSERT INTO users (id, name, email) VALUES
('guest', 'Guest User', 'guest@example.com')
ON DUPLICATE KEY UPDATE name=VALUES(name);
