-- =====================================================================
-- SQLTools Schema Inspector: AWS EC2 MySQL (rag_users)
-- Run this in SQLTools (Ctrl+E Ctrl+E or click "Run on active connection")
-- =====================================================================

USE rag_users;

-- 1. List all tables in rag_users
SHOW TABLES;

-- 2. Full Column Schema (Names, Data Types, Nullable, Default, Key)
SELECT 
    TABLE_NAME AS 'Table',
    COLUMN_NAME AS 'Column',
    COLUMN_TYPE AS 'Type',
    IS_NULLABLE AS 'Nullable',
    COLUMN_KEY AS 'Key',
    COLUMN_DEFAULT AS 'Default',
    EXTRA AS 'Extra'
FROM 
    INFORMATION_SCHEMA.COLUMNS
WHERE 
    TABLE_SCHEMA = 'rag_users'
ORDER BY 
    TABLE_NAME, ORDINAL_POSITION;

-- 3. Foreign Key Relationships & Cascade Rules
SELECT 
    TABLE_NAME AS 'Child Table',
    COLUMN_NAME AS 'Foreign Key Column',
    CONSTRAINT_NAME AS 'Constraint Name',
    REFERENCED_TABLE_NAME AS 'Parent Table (Referenced)',
    REFERENCED_COLUMN_NAME AS 'Parent Column (Referenced)'
FROM 
    INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE 
    TABLE_SCHEMA = 'rag_users' 
    AND REFERENCED_TABLE_NAME IS NOT NULL;

-- 4. Indexes & Unique Constraints
SELECT 
    TABLE_NAME AS 'Table',
    INDEX_NAME AS 'Index Name',
    NON_UNIQUE AS 'Non-Unique',
    COLUMN_NAME AS 'Indexed Column',
    INDEX_TYPE AS 'Type'
FROM 
    INFORMATION_SCHEMA.STATISTICS
WHERE 
    TABLE_SCHEMA = 'rag_users'
ORDER BY 
    TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- 5. Quick Row Counts per Table
SELECT 'users' AS table_name, COUNT(*) AS total_records FROM users
UNION ALL
SELECT 'purchases' AS table_name, COUNT(*) AS total_records FROM purchases
UNION ALL
SELECT 'past_records' AS table_name, COUNT(*) AS total_records FROM past_records
UNION ALL
SELECT 'conversation_turns' AS table_name, COUNT(*) AS total_records FROM conversation_turns;
