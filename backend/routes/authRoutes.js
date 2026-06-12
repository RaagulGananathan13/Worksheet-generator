import { Router } from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { randomUUID } from 'crypto';
import { requireAuth } from '../middleware/authMiddleware.js';
import { getPool } from '../services/db.js';

const JWT_SECRET = process.env.JWT_SECRET || 'geniusbees-worksheet-secret-dev-2026';
const JWT_EXPIRES_IN = '7d';

// Email validation regex: geniusbees.devXX@gmail.com where XX is 1-3 digits
const VALID_EMAIL_REGEX = /^geniusbees\.dev\d{1,3}@gmail\.com$/i;

const router = Router();

// ─── Helpers ───────────────────────────────────────────────

function generateToken(user) {
  return jwt.sign(
    { id: user.id, email: user.email },
    JWT_SECRET,
    { expiresIn: JWT_EXPIRES_IN }
  );
}

// ─── POST /api/auth/signup ─────────────────────────────────

router.post('/signup', async (req, res) => {
  try {
    const { email, password } = req.body;

    // Validate required fields
    if (!email || !password) {
      return res.status(400).json({ message: 'Email and password are required.' });
    }

    // Validate email format
    const emailLower = email.trim().toLowerCase();
    if (!VALID_EMAIL_REGEX.test(emailLower)) {
      return res.status(400).json({
        message: 'Invalid email. Only geniusbees.devXX@gmail.com emails are allowed (e.g., geniusbees.dev01@gmail.com).',
      });
    }

    // Validate password strength
    if (password.length < 6) {
      return res.status(400).json({ message: 'Password must be at least 6 characters long.' });
    }

    // Check if user already exists
    const pool = getPool();
    const [existing] = await pool.execute('SELECT id FROM users WHERE email = ?', [emailLower]);
    if (existing.length > 0) {
      return res.status(409).json({ message: 'An account with this email already exists.' });
    }

    // Hash password and create user
    const salt = await bcrypt.genSalt(10);
    const passwordHash = await bcrypt.hash(password, salt);
    const userId = randomUUID();

    await pool.execute(
      'INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)',
      [userId, emailLower, passwordHash]
    );

    const newUser = { id: userId, email: emailLower };
    const token = generateToken(newUser);

    res.status(201).json({
      message: 'Account created successfully.',
      token,
      user: newUser,
    });
  } catch (error) {
    console.error('Signup error:', error);
    res.status(500).json({ message: 'Failed to create account.' });
  }
});

// ─── POST /api/auth/login ──────────────────────────────────

router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ message: 'Email and password are required.' });
    }

    const emailLower = email.trim().toLowerCase();
    const pool = getPool();
    const [rows] = await pool.execute('SELECT * FROM users WHERE email = ?', [emailLower]);

    if (rows.length === 0) {
      return res.status(401).json({ message: 'Invalid email or password.' });
    }

    const user = rows[0];
    const isMatch = await bcrypt.compare(password, user.password_hash);
    if (!isMatch) {
      return res.status(401).json({ message: 'Invalid email or password.' });
    }

    const token = generateToken({ id: user.id, email: user.email });

    res.json({
      message: 'Login successful.',
      token,
      user: { id: user.id, email: user.email },
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ message: 'Failed to log in.' });
  }
});

// ─── GET /api/auth/me ──────────────────────────────────────

router.get('/me', requireAuth, async (req, res) => {
  try {
    const pool = getPool();
    const [rows] = await pool.execute('SELECT id, email, created_at FROM users WHERE id = ?', [req.user.id]);

    if (rows.length === 0) {
      return res.status(404).json({ message: 'User not found.' });
    }

    const user = rows[0];
    res.json({
      user: { id: user.id, email: user.email, createdAt: user.created_at },
    });
  } catch (error) {
    console.error('Me error:', error);
    res.status(500).json({ message: 'Failed to fetch user.' });
  }
});

export default router;
