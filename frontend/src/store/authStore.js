import { create } from 'zustand';

const API_BASE = '/api/auth';

const useAuthStore = create((set, get) => ({
  // === State ===
  user: null,
  token: localStorage.getItem('gb_token') || sessionStorage.getItem('gb_token') || null,
  isAuthenticated: false,
  isLoading: true, // True on initial app load to check stored token
  error: '',

  // === Actions ===

  /**
   * Check stored token validity on app mount.
   */
  initialize: async () => {
    const token = localStorage.getItem('gb_token') || sessionStorage.getItem('gb_token');
    if (!token) {
      set({ isLoading: false, isAuthenticated: false });
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        throw new Error('Invalid token');
      }

      const data = await res.json();
      set({
        user: data.user,
        token,
        isAuthenticated: true,
        isLoading: false,
        error: '',
      });
    } catch {
      // Token expired or invalid — clean up
      localStorage.removeItem('gb_token');
      sessionStorage.removeItem('gb_token');
      set({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
        error: '',
      });
    }
  },

  /**
   * Sign up with email + password.
   */
  signup: async (email, password) => {
    set({ error: '', isLoading: true });

    try {
      const res = await fetch(`${API_BASE}/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        set({ error: data.message || 'Signup failed.', isLoading: false });
        return false;
      }

      localStorage.setItem('gb_token', data.token);
      set({
        user: data.user,
        token: data.token,
        isAuthenticated: true,
        isLoading: false,
        error: '',
      });
      return true;
    } catch (err) {
      set({ error: 'Network error. Please try again.', isLoading: false });
      return false;
    }
  },

  /**
   * Log in with email + password.
   */
  login: async (email, password, rememberMe = false) => {
    set({ error: '', isLoading: true });

    try {
      const res = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        set({ error: data.message || 'Login failed.', isLoading: false });
        return false;
      }

      if (rememberMe) {
        localStorage.setItem('gb_token', data.token);
      } else {
        sessionStorage.setItem('gb_token', data.token);
      }
      set({
        user: data.user,
        token: data.token,
        isAuthenticated: true,
        isLoading: false,
        error: '',
      });
      return true;
    } catch (err) {
      set({ error: 'Network error. Please try again.', isLoading: false });
      return false;
    }
  },

  /**
   * Log out — clear token and user state.
   */
  logout: () => {
    localStorage.removeItem('gb_token');
    sessionStorage.removeItem('gb_token');
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      error: '',
    });
  },

  /**
   * Clear error message.
   */
  clearError: () => set({ error: '' }),

  /**
   * Forgot Password
   */
  forgotPassword: async (email) => {
    set({ error: '', isLoading: true });
    try {
      const res = await fetch(`${API_BASE}/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) {
        set({ error: data.message || 'Failed to send reset link.', isLoading: false });
        return { success: false };
      }
      set({ isLoading: false });
      return { success: true, devToken: data.devToken };
    } catch (err) {
      set({ error: 'Network error.', isLoading: false });
      return { success: false };
    }
  },

  /**
   * Reset Password
   */
  resetPassword: async (email, token, newPassword) => {
    set({ error: '', isLoading: true });
    try {
      const res = await fetch(`${API_BASE}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, token, newPassword }),
      });
      const data = await res.json();
      if (!res.ok) {
        set({ error: data.message || 'Failed to reset password.', isLoading: false });
        return false;
      }
      set({ isLoading: false });
      return true;
    } catch (err) {
      set({ error: 'Network error.', isLoading: false });
      return false;
    }
  },
}));

export default useAuthStore;
