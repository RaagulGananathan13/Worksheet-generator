import { useState, useCallback, useEffect } from 'react';
import { Mail, Lock, Eye, EyeOff, LogIn, UserPlus, AlertCircle, ArrowRight, Loader2, CheckCircle2, KeyRound } from 'lucide-react';
import useAuthStore from '../../store/authStore';

const EMAIL_REGEX = /^geniusbees\.dev\d{1,3}@gmail\.com$/i;

export default function AuthPage() {
  const [mode, setMode] = useState('login'); // 'login' | 'signup' | 'forgot-password' | 'reset-password'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  
  // New states for Remember Me & Password Reset
  const [rememberMe, setRememberMe] = useState(false);
  const [resetToken, setResetToken] = useState('');

  const login = useAuthStore((s) => s.login);
  const signup = useAuthStore((s) => s.signup);
  const forgotPassword = useAuthStore((s) => s.forgotPassword);
  const resetPassword = useAuthStore((s) => s.resetPassword);
  const error = useAuthStore((s) => s.error);
  const isLoading = useAuthStore((s) => s.isLoading);
  const clearError = useAuthStore((s) => s.clearError);

  const switchMode = useCallback((newMode) => {
    setMode(newMode);
    setLocalError('');
    setSuccessMsg('');
    clearError();
    setPassword('');
    setConfirmPassword('');
    if (newMode === 'login' || newMode === 'signup') {
      setResetToken('');
    }
  }, [clearError]);

  const handleSubmit = useCallback(
    async (e) => {
      e.preventDefault();
      setLocalError('');
      setSuccessMsg('');
      clearError();

      // Common Validation
      if (mode !== 'reset-password' && !email.trim()) {
        setLocalError('Please enter your email.');
        return;
      }
      if (mode !== 'reset-password' && !EMAIL_REGEX.test(email.trim().toLowerCase())) {
        setLocalError('Email must match geniusbees.devXX@gmail.com');
        return;
      }

      if (mode === 'login') {
        if (!password) {
          setLocalError('Please enter your password.');
          return;
        }
        await login(email.trim().toLowerCase(), password, rememberMe);
      } 
      else if (mode === 'signup') {
        if (password.length < 6) {
          setLocalError('Password must be at least 6 characters.');
          return;
        }
        if (password !== confirmPassword) {
          setLocalError('Passwords do not match.');
          return;
        }
        await signup(email.trim().toLowerCase(), password);
      }
      else if (mode === 'forgot-password') {
        const res = await forgotPassword(email.trim().toLowerCase());
        if (res.success) {
          setSuccessMsg('Reset link generated!');
          // In DEV, we get the token directly
          if (res.devToken) {
            setResetToken(res.devToken);
            setTimeout(() => {
              switchMode('reset-password');
            }, 1500);
          }
        }
      }
      else if (mode === 'reset-password') {
        if (!resetToken) {
          setLocalError('Reset token is missing.');
          return;
        }
        if (password.length < 6) {
          setLocalError('Password must be at least 6 characters.');
          return;
        }
        if (password !== confirmPassword) {
          setLocalError('Passwords do not match.');
          return;
        }
        const success = await resetPassword(email.trim().toLowerCase(), resetToken, password);
        if (success) {
          setSuccessMsg('Password reset successful! You can now log in.');
          setTimeout(() => {
            switchMode('login');
          }, 2000);
        }
      }
    },
    [email, password, confirmPassword, mode, rememberMe, resetToken, login, signup, forgotPassword, resetPassword, clearError, switchMode]
  );

  const displayError = localError || error;

  return (
    <div className="h-full flex items-center justify-center bg-gradient-to-br from-surface-50 via-white to-accent-50 animate-fade-in">
      {/* Background decorative elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-accent-100/40 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-accent-200/30 rounded-full blur-3xl" />
        <div className="absolute top-1/4 left-1/4 w-60 h-60 bg-brand-green/5 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md mx-4">
        {/* Logo + Branding */}
        <div className="text-center mb-8 animate-slide-up">
          <div className="inline-flex items-center justify-center mb-4">
            <img
              src="/gb-logo.jpg"
              alt="GeniusBees"
              className="h-14 object-contain"
            />
          </div>
          <h1 className="text-2xl font-bold text-surface-900 mb-1">
            Worksheet Generator
          </h1>
          <p className="text-sm text-surface-500">
            {mode === 'login' && 'Sign in to your account'}
            {mode === 'signup' && 'Create your developer account'}
            {mode === 'forgot-password' && 'Recover your password'}
            {mode === 'reset-password' && 'Set a new password'}
          </p>
        </div>

        {/* Auth Card */}
        <div className="bg-white rounded-2xl shadow-xl border border-surface-200/80 p-8 animate-slide-up"
             style={{ animationDelay: '0.1s' }}>
          
          {/* Mode Toggle (Only show in Login/Signup) */}
          {(mode === 'login' || mode === 'signup') && (
            <div className="flex bg-surface-100 rounded-xl p-1 mb-6">
              <button
                onClick={() => mode !== 'login' && switchMode('login')}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all duration-300 ${
                  mode === 'login'
                    ? 'bg-white text-surface-900 shadow-sm'
                    : 'text-surface-500 hover:text-surface-700'
                }`}
              >
                <LogIn className="w-4 h-4" />
                Sign In
              </button>
              <button
                onClick={() => mode !== 'signup' && switchMode('signup')}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all duration-300 ${
                  mode === 'signup'
                    ? 'bg-white text-surface-900 shadow-sm'
                    : 'text-surface-500 hover:text-surface-700'
                }`}
              >
                <UserPlus className="w-4 h-4" />
                Sign Up
              </button>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-xs font-semibold text-surface-600 uppercase tracking-wider mb-1.5">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                <input
                  type="email"
                  value={email}
                  disabled={mode === 'reset-password'}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="geniusbees.dev01@gmail.com"
                  className="w-full pl-10 pr-4 py-3 bg-surface-50 border border-surface-200 rounded-xl text-sm text-surface-900
                             placeholder:text-surface-400 disabled:opacity-50
                             focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50
                             transition-all duration-200"
                  autoComplete="email"
                />
              </div>
            </div>

            {/* Token (Reset Password only) */}
            {mode === 'reset-password' && (
              <div>
                <label className="block text-xs font-semibold text-surface-600 uppercase tracking-wider mb-1.5">
                  Reset Token
                </label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                  <input
                    type="text"
                    value={resetToken}
                    onChange={(e) => setResetToken(e.target.value)}
                    placeholder="Enter reset token"
                    className="w-full pl-10 pr-4 py-3 bg-surface-50 border border-surface-200 rounded-xl text-sm text-surface-900
                               placeholder:text-surface-400
                               focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50"
                  />
                </div>
              </div>
            )}

            {/* Password (Login, Signup, Reset) */}
            {mode !== 'forgot-password' && (
              <div>
                <label className="block text-xs font-semibold text-surface-600 uppercase tracking-wider mb-1.5">
                  {mode === 'reset-password' ? 'New Password' : 'Password'}
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full pl-10 pr-11 py-3 bg-surface-50 border border-surface-200 rounded-xl text-sm text-surface-900
                               placeholder:text-surface-400
                               focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50
                               transition-all duration-200"
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600 transition-colors"
                    tabIndex={-1}
                  >
                    {showPassword ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Confirm Password (Signup, Reset) */}
            {(mode === 'signup' || mode === 'reset-password') && (
              <div className="animate-fade-in">
                <label className="block text-xs font-semibold text-surface-600 uppercase tracking-wider mb-1.5">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full pl-10 pr-4 py-3 bg-surface-50 border border-surface-200 rounded-xl text-sm text-surface-900
                               placeholder:text-surface-400
                               focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50
                               transition-all duration-200"
                    autoComplete="new-password"
                  />
                </div>
              </div>
            )}

            {/* Login Extras: Remember Me & Forgot Password */}
            {mode === 'login' && (
              <div className="flex items-center justify-between mt-2">
                <label className="flex items-center gap-2 cursor-pointer group">
                  <div className="relative flex items-center justify-center">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="peer appearance-none w-4 h-4 border border-surface-300 rounded bg-white checked:bg-brand-orange checked:border-brand-orange transition-colors cursor-pointer"
                    />
                    <CheckCircle2 className="absolute w-3 h-3 text-white opacity-0 peer-checked:opacity-100 pointer-events-none transition-opacity" />
                  </div>
                  <span className="text-xs text-surface-600 group-hover:text-surface-900 transition-colors select-none">
                    Remember me
                  </span>
                </label>

                <button
                  type="button"
                  onClick={() => switchMode('forgot-password')}
                  className="text-xs font-medium text-brand-orange hover:text-brand-orange-dark transition-colors"
                >
                  Forgot Password?
                </button>
              </div>
            )}

            {/* Back to Login (Forgot / Reset) */}
            {(mode === 'forgot-password' || mode === 'reset-password') && (
              <div className="flex justify-end mt-2">
                <button
                  type="button"
                  onClick={() => switchMode('login')}
                  className="text-xs font-medium text-surface-500 hover:text-surface-700 transition-colors"
                >
                  Back to Sign In
                </button>
              </div>
            )}

            {/* Error Message */}
            {displayError && (
              <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-red-50 border border-red-200 text-xs text-danger-500 animate-fade-in">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{displayError}</span>
              </div>
            )}

            {/* Success Message */}
            {successMsg && (
              <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-green-50 border border-green-200 text-xs text-green-700 animate-fade-in">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{successMsg}</span>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2 py-3 mt-4 rounded-xl font-semibold text-sm text-white
                         bg-gradient-to-r from-brand-orange to-brand-orange-dark
                         hover:from-brand-orange-dark hover:to-brand-orange-dark
                         shadow-lg shadow-brand-orange/25 hover:shadow-brand-orange/40
                         transition-all duration-300 active:scale-[0.98]
                         disabled:opacity-60 disabled:cursor-not-allowed disabled:shadow-none"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {mode === 'login' && 'Signing in...'}
                  {mode === 'signup' && 'Creating account...'}
                  {mode === 'forgot-password' && 'Sending link...'}
                  {mode === 'reset-password' && 'Resetting...'}
                </>
              ) : (
                <>
                  {mode === 'login' && 'Sign In'}
                  {mode === 'signup' && 'Create Account'}
                  {mode === 'forgot-password' && 'Send Reset Link'}
                  {mode === 'reset-password' && 'Reset Password'}
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-surface-400 mt-6">
          GeniusBees Inc. © {new Date().getFullYear()} • Worksheet Generator
        </p>
      </div>
    </div>
  );
}

