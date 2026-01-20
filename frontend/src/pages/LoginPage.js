import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Lock, Mail, User, KeyRound } from 'lucide-react';
import { authAPI } from '../lib/api';

const LoginPage = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [showOTPStep, setShowOTPStep] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    full_name: '',
    otp: ''
  });
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleSendOTP = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      // First, send OTP for verification
      await authAPI.sendOTP(formData.email);
      toast.success('Verification code sent to your email');
      setShowOTPStep(true);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to send verification code');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyAndRegister = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      // Verify OTP first
      await authAPI.verifyOTP(formData.email, formData.otp);
      
      // Then register the user
      await register(formData.email, formData.password, formData.full_name);
      toast.success('Registration successful');
      navigate('/dashboard');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await login(formData.email, formData.password);
      toast.success('Login successful');
      navigate('/dashboard');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  const handleResendOTP = async () => {
    setLoading(true);
    try {
      await authAPI.sendOTP(formData.email);
      toast.success('Verification code resent');
    } catch (error) {
      toast.error('Failed to resend code');
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = () => {
    if (!formData.email) {
      toast.error('Please enter your email first');
      return;
    }
    navigate('/forgot-password', { state: { email: formData.email } });
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8 bg-[#121212]">
        <div className="w-full max-w-md">
          <div className="mb-8">
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
              WhatsApp CRM Pro
            </h1>
            <p className="text-muted-foreground">
              Manage your bulk messaging campaigns efficiently
            </p>
          </div>

          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-8">
            <div className="mb-6">
              <h2 className="text-2xl font-semibold mb-2">
                {isLogin ? 'Sign In' : 'Create Account'}
              </h2>
              <p className="text-sm text-muted-foreground">
                {isLogin ? 'Welcome back!' : 'Get started with your account'}
              </p>
            </div>

            <form onSubmit={isLogin ? handleLogin : (showOTPStep ? handleVerifyAndRegister : handleSendOTP)} className="space-y-4" data-testid="login-form">
              {!isLogin && !showOTPStep && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Full Name
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <input
                      data-testid="full-name-input"
                      type="text"
                      value={formData.full_name}
                      onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                      className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 pl-10 pr-3 text-sm transition-colors outline-none"
                      placeholder="John Doe"
                      required
                    />
                  </div>
                </div>
              )}

              {!showOTPStep && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Email
                    </label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <input
                        data-testid="email-input"
                        type="email"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 pl-10 pr-3 text-sm transition-colors outline-none"
                        placeholder="you@example.com"
                        required
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Password
                    </label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <input
                        data-testid="password-input"
                        type="password"
                        value={formData.password}
                        onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                        className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 pl-10 pr-3 text-sm transition-colors outline-none"
                        placeholder="••••••••"
                        required
                      />
                    </div>
                    {isLogin && (
                      <div className="mt-2 text-right">
                        <button
                          type="button"
                          onClick={handleForgotPassword}
                          className="text-sm text-[#3ECF8E] hover:text-[#34B27B] transition-colors"
                        >
                          Forgot Password?
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}

              {!isLogin && showOTPStep && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Verification Code
                  </label>
                  <p className="text-xs text-muted-foreground mb-3">
                    Enter the 6-digit code sent to {formData.email}
                  </p>
                  <div className="relative">
                    <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <input
                      type="text"
                      value={formData.otp}
                      onChange={(e) => setFormData({ ...formData, otp: e.target.value })}
                      className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 pl-10 pr-3 text-sm transition-colors outline-none text-center tracking-widest font-mono text-lg"
                      placeholder="000000"
                      maxLength={6}
                      required
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleResendOTP}
                    disabled={loading}
                    className="text-sm text-[#3ECF8E] hover:text-[#34B27B] transition-colors mt-2"
                  >
                    Resend Code
                  </button>
                </div>
              )}

              <button
                data-testid="submit-button"
                type="submit"
                disabled={loading}
                className="w-full bg-[#3ECF8E] text-black hover:bg-[#34B27B] font-medium rounded-md h-10 shadow-[0_0_10px_rgba(62,207,142,0.2)] transition-all disabled:opacity-50"
              >
                {loading ? 'Please wait...' : (
                  isLogin ? 'Sign In' : (showOTPStep ? 'Verify & Create Account' : 'Send Verification Code')
                )}
              </button>
            </form>

            <div className="mt-6 text-center">
              {showOTPStep && (
                <button
                  onClick={() => {
                    setShowOTPStep(false);
                    setFormData({ ...formData, otp: '' });
                  }}
                  className="text-sm text-muted-foreground hover:text-white transition-colors mb-3 block"
                >
                  ← Change Email
                </button>
              )}
              <button
                data-testid="toggle-mode-button"
                onClick={() => {
                  setIsLogin(!isLogin);
                  setShowOTPStep(false);
                  setFormData({ email: '', password: '', full_name: '', otp: '' });
                }}
                className="text-sm text-muted-foreground hover:text-white transition-colors"
              >
                {isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Image */}
      <div 
        className="hidden lg:block lg:w-1/2 bg-cover bg-center relative"
        style={{ backgroundImage: 'url(https://images.unsplash.com/photo-1762278804768-7109128de73f?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzh8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMGRpZ2l0YWwlMjBuZXR3b3JrJTIwZ3JlZW4lMjBkYXJrJTIwYmFja2dyb3VuZHxlbnwwfHx8fDE3NjgxMzQ0MzB8MA&ixlib=rb-4.1.0&q=85)' }}
      >
        <div className="absolute inset-0 bg-black/80"></div>
        <div className="absolute inset-0 flex items-center justify-center p-12">
          <div className="text-center">
            <h2 className="text-5xl font-bold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Reach Thousands<br />In Minutes
            </h2>
            <p className="text-xl text-muted-foreground">
              Powerful bulk messaging with smart customer classification
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
