import { create } from 'zustand';

const API_BASE = '/api/auth';

const useAuthStore = create((set, get) => ({
  // === State ===
  user: null,
  token: localStorage.getItem('gb_token') || null,
  isAuthenticated: false,
  isLoading: true, // True on initial app load to check stored token
  error: '',

  // === Actions ===

  /**
   * Check stored token validity on app mount.
   */
  initialize: async () => {
    const token = localStorage.getItem('gb_token');
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
  login: async (email, password) => {
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
   * Log out — clear token and user state.
   */
  logout: () => {
    localStorage.removeItem('gb_token');
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
}));

export default useAuthStore;
