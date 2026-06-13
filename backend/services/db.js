import mysql from 'mysql2/promise';

let pool = null;

/**
 * Initialize MySQL: create database if missing, create tables, return pool.
 */
export async function initDatabase() {
  const host = process.env.DB_HOST || 'localhost';
  const user = process.env.DB_USER || 'root';
  const password = process.env.DB_PASSWORD;
  const database = process.env.DB_NAME || 'worksheet_generator';

  // 1. Connect without database to create it if needed
  const tempConn = await mysql.createConnection({ host, user, password });
  await tempConn.execute(`CREATE DATABASE IF NOT EXISTS \`${database}\``);
  await tempConn.end();

  // 2. Create pool connected to the database
  pool = mysql.createPool({
    host,
    user,
    password,
    database,
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0,
  });

  // 3. Create tables
  await pool.execute(`
    CREATE TABLE IF NOT EXISTS users (
      id VARCHAR(36) PRIMARY KEY,
      email VARCHAR(255) UNIQUE NOT NULL,
      password_hash VARCHAR(255) NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await pool.execute(`
    CREATE TABLE IF NOT EXISTS worksheets (
      id VARCHAR(36) PRIMARY KEY,
      file_name VARCHAR(255) NOT NULL,
      activity_name VARCHAR(255) DEFAULT 'general',
      activity_folder VARCHAR(255) DEFAULT 'general',
      s3_html_key VARCHAR(512) NOT NULL,
      s3_pdf_key VARCHAR(512),
      owner_id VARCHAR(36) NOT NULL,
      owner_email VARCHAR(255) NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
    )
  `);

  console.log(`✓ Connected to MySQL database: ${database}`);
  return pool;
}

/**
 * Get the MySQL connection pool. Must call initDatabase() first.
 */
export function getPool() {
  if (!pool) {
    throw new Error('Database not initialized. Call initDatabase() first.');
  }
  return pool;
}
