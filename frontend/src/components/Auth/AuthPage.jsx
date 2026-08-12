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
    <div className="h-full min-h-screen flex bg-white animate-fade-in">
      
      {/* Left Panel: Hero Banner (Hidden on Mobile) */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-gradient-to-br from-brand-yellow/30 to-brand-green/20 flex-col justify-between overflow-hidden">
        {/* Decorative elements */}
        <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -left-40 w-96 h-96 bg-brand-yellow/40 rounded-full blur-3xl mix-blend-multiply" />
          <div className="absolute top-1/2 -right-20 w-80 h-80 bg-brand-green/30 rounded-full blur-3xl mix-blend-multiply" />
        </div>

        {/* Hero Content */}
        <div className="relative z-10 flex flex-col items-start px-16 pt-16 h-full justify-center">
          <img
            src="/gb-logo.jpg"
            alt="GeniusBees"
            className="h-16 object-contain mb-10"
          />
          <h1 className="text-5xl font-extrabold text-surface-900 mb-4 leading-tight tracking-tight">
            Welcome to <br />
            <span className="text-brand-orange">GeniusBees</span>
          </h1>
          <p className="text-lg text-surface-600 mb-12 max-w-md font-medium leading-relaxed">
            Start your child's journey to success with GeniusBees. <br/>
            Together, let's shape brighter, smarter futures!
          </p>
          
          <div className="relative w-full flex-1 min-h-0 mt-6 pb-2 flex justify-center items-end">
            {/* The new hero illustration, optimized as webp */}
            <img 
              src="/assets/illustrations/hero_illustration.webp" 
              alt="GeniusBees Learning" 
              className="max-w-full max-h-full object-contain drop-shadow-2xl animate-float scale-110 origin-bottom"
              loading="eager"
            />
          </div>
        </div>
      </div>

      {/* Right Panel: Auth Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 sm:p-12 bg-white relative">
        <div className="w-full max-w-md">
          {/* Logo (Mobile Only) */}
          <div className="lg:hidden text-center mb-8 animate-slide-up">
            <img
              src="/gb-logo.jpg"
              alt="GeniusBees"
              className="h-14 object-contain mx-auto mb-4"
            />
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

          <div className="hidden lg:block mb-8 animate-slide-up">
            <h2 className="text-3xl font-bold text-surface-900 mb-2">
              Worksheet Generator
            </h2>
            <p className="text-surface-500 font-medium">
              {mode === 'login' && 'Sign in to your account'}
              {mode === 'signup' && 'Create your developer account'}
              {mode === 'forgot-password' && 'Recover your password'}
              {mode === 'reset-password' && 'Set a new password'}
            </p>
          </div>

          {/* Auth Card */}
          <div className="bg-white rounded-3xl sm:shadow-[0_8px_30px_rgb(0,0,0,0.04)] sm:border border-surface-100 sm:p-10 p-2 animate-slide-up"
               style={{ animationDelay: '0.1s' }}>
            
            {/* Mode Toggle (Only show in Login/Signup) */}
            {(mode === 'login' || mode === 'signup') && (
              <div className="flex bg-surface-50 rounded-xl p-1.5 mb-8 border border-surface-100">
                <button
                  onClick={() => mode !== 'login' && switchMode('login')}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all duration-300 ${
                    mode === 'login'
                      ? 'bg-white text-surface-900 shadow-sm border border-surface-200/50'
                      : 'text-surface-500 hover:text-surface-700'
                  }`}
                >
                  <LogIn className="w-4 h-4" />
                  Sign In
                </button>
                <button
                  onClick={() => mode !== 'signup' && switchMode('signup')}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all duration-300 ${
                    mode === 'signup'
                      ? 'bg-white text-surface-900 shadow-sm border border-surface-200/50'
                      : 'text-surface-500 hover:text-surface-700'
                  }`}
                >
                  <UserPlus className="w-4 h-4" />
                  Sign Up
                </button>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Email */}
              <div>
                <label className="block text-xs font-bold text-surface-700 uppercase tracking-wider mb-2">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                  <input
                    type="email"
                    value={email}
                    disabled={mode === 'reset-password'}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="geniusbees.dev01@gmail.com"
                    className="w-full pl-11 pr-4 py-3.5 bg-surface-50/50 border border-surface-200 rounded-xl text-sm text-surface-900
                               placeholder:text-surface-400 disabled:opacity-50 font-medium
                               focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50 focus:bg-white
                               transition-all duration-200"
                    autoComplete="email"
                  />
                </div>
              </div>

              {/* Token (Reset Password only) */}
              {mode === 'reset-password' && (
                <div>
                  <label className="block text-xs font-bold text-surface-700 uppercase tracking-wider mb-2">
                    Reset Token
                  </label>
                  <div className="relative">
                    <KeyRound className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                    <input
                      type="text"
                      value={resetToken}
                      onChange={(e) => setResetToken(e.target.value)}
                      placeholder="Enter reset token"
                      className="w-full pl-11 pr-4 py-3.5 bg-surface-50/50 border border-surface-200 rounded-xl text-sm text-surface-900
                                 placeholder:text-surface-400 font-medium
                                 focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50 focus:bg-white"
                    />
                  </div>
                </div>
              )}

              {/* Password (Login, Signup, Reset) */}
              {mode !== 'forgot-password' && (
                <div>
                  <label className="block text-xs font-bold text-surface-700 uppercase tracking-wider mb-2">
                    {mode === 'reset-password' ? 'New Password' : 'Password'}
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-11 pr-12 py-3.5 bg-surface-50/50 border border-surface-200 rounded-xl text-sm text-surface-900
                                 placeholder:text-surface-400 font-medium
                                 focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50 focus:bg-white
                                 transition-all duration-200"
                      autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600 transition-colors p-1"
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
                  <label className="block text-xs font-bold text-surface-700 uppercase tracking-wider mb-2">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-11 pr-4 py-3.5 bg-surface-50/50 border border-surface-200 rounded-xl text-sm text-surface-900
                                 placeholder:text-surface-400 font-medium
                                 focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/50 focus:bg-white
                                 transition-all duration-200"
                      autoComplete="new-password"
                    />
                  </div>
                </div>
              )}

              {/* Login Extras: Remember Me & Forgot Password */}
              {mode === 'login' && (
                <div className="flex items-center justify-between mt-2 pt-1">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <div className="relative flex items-center justify-center">
                      <input
                        type="checkbox"
                        checked={rememberMe}
                        onChange={(e) => setRememberMe(e.target.checked)}
                        className="peer appearance-none w-4.5 h-4.5 border-2 border-surface-300 rounded bg-white checked:bg-brand-orange checked:border-brand-orange transition-colors cursor-pointer"
                      />
                      <CheckCircle2 className="absolute w-3 h-3 text-white opacity-0 peer-checked:opacity-100 pointer-events-none transition-opacity" />
                    </div>
                    <span className="text-sm font-medium text-surface-600 group-hover:text-surface-900 transition-colors select-none">
                      Remember me
                    </span>
                  </label>

                  <button
                    type="button"
                    onClick={() => switchMode('forgot-password')}
                    className="text-sm font-semibold text-brand-orange hover:text-brand-orange-dark transition-colors"
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
                    className="text-sm font-semibold text-surface-500 hover:text-surface-700 transition-colors"
                  >
                    Back to Sign In
                  </button>
                </div>
              )}

              {/* Error Message */}
              {displayError && (
                <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-sm font-medium text-danger-600 animate-fade-in">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-danger-500" />
                  <span>{displayError}</span>
                </div>
              )}

              {/* Success Message */}
              {successMsg && (
                <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-green-50 border border-green-100 text-sm font-medium text-green-700 animate-fade-in">
                  <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5 text-green-600" />
                  <span>{successMsg}</span>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isLoading}
                className="w-full flex items-center justify-center gap-2 py-3.5 mt-6 rounded-xl font-bold text-sm text-white
                           bg-brand-orange hover:bg-brand-orange-dark
                           shadow-[0_4px_14px_0_rgba(249,115,22,0.39)] hover:shadow-[0_6px_20px_rgba(249,115,22,0.23)] hover:-translate-y-0.5
                           transition-all duration-200 active:scale-[0.98]
                           disabled:opacity-60 disabled:cursor-not-allowed disabled:shadow-none disabled:transform-none"
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
          <p className="text-center text-[12px] font-medium text-surface-400 mt-10">
            GeniusBees Inc. © {new Date().getFullYear()} • Worksheet Generator
          </p>
        </div>
      </div>
    </div>
  );
}

